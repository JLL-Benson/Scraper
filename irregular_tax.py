"""
Created on May 11th 2019

@author: Benson.Chen benson.chen@ap.jll.com
"""


import re
import requests
import db2 as db
import pagemanipulate as pm
import utility_email as em
from PIL import Image
from baidu_api import Baidu_ocr
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utility_commons import *
import keys

SCREENSHOT_PATH = PIC_DIR + r'\screen_shot.png'
VCODE_PATH = PIC_DIR + r'\vcode.png'
TAX_DETAIL_PATH = FILE_DIR + r'\Irregular_Tax.xls'
TAX_PATH = FILE_DIR + r'\Irregular_Tax_Summary.xls'
ATTACHMENT_PATH = FILE_DIR + r'\{}_异常发票清单_{}.xlsx'

SITE = 'Irregular_Tax'
TAX_DETAIL_TABLE = 'Scrapy_' + SITE
TAX_TABLE = 'Scrapy_' + SITE + '_Summary'
ACCESS_TABLE_NAME = 'Scrapy_Irregular_Tax_Access'
LOG_PATH = LOG_DIR + '\\' + SITE + '.log'

logger = getLogger(SITE)
count = 0


class Tax:

    def __init__(self, link, username, password):

        self.base = link
        self.username = username
        self.password = password
        self.web = pm.Page(self.base, 'normal')
        self.web.driver.implicitly_wait(10)
        self.session = requests.session()
        self.cookies = requests.cookies.RequestsCookieJar()

    # Crop validation code pic from screen shot
    def get_vcode_pic(self):
        try:
            self.web.driver.save_screenshot(SCREENSHOT_PATH)
            pic = self.web.driver.find_element_by_xpath('//*[@id="crcpic"]')
        except Exception as e:
            logger.exception('Unable to get validation code pic.')
            return False
        vcode_pic = Image.open(SCREENSHOT_PATH)
        vcode_pic = vcode_pic.crop((pic.location['x'], pic.location['y'], pic.location['x'] + pic.size['width'], pic.location['y'] + pic.size['height']))
        return vcode_pic

    # Validation code is valid with 4 letters and probability > 0.7
    def vcode_validate(self, result, threshold=0.7):
        if not result:
            return None
        vcode = result['words_result'][0]['words'].replace(' ', '')
        prop = result['words_result'][0]['probability']['average']
        vcode = ''.join(re.findall(re.compile('[A-Za-z0-9]+'), vcode))
        if (len(vcode) == 4) and prop > threshold:
            return vcode
        else:
            return False

    # Not return validation code until get valid one
    def get_vcode(self):
        global count
        while True:

            logger.info('Try {} times.'.format(count))
            count += 1
            if count % 100 == 0:
                return False

            vpic = self.get_vcode_pic()
            if vpic:
                ocr = Baidu_ocr()
                ocr_result = ocr.ocr_api_call(vpic, VCODE_PATH, bin_threshold=100, detect_direction='false', language_type='ENG', probability='true')
                if (not ocr_result) and (ocr.switch < 4):
                    continue
                elif (not ocr_result) and (ocr.switch >= 4):
                    exit(1)
                vcode = self.vcode_validate(ocr_result)
                if vcode:
                    logger.info('Get validation code "{}". Try to login.'.format(vcode))
                    return vcode
                else:
                    # logger.info('Cannot recognize validation code, try again.')
                    try:
                        self.web.driver.find_element_by_xpath('//*[@id="crcpic"]').click()
                    except Exception as e:
                        logger.exception('Unable to refresh validation code pic.\n{}'.format(e))
                        return False
            else:
                return False

    # Login
    def login(self):
        while True:

            vcode = self.get_vcode()
            if vcode:
                try:
                    self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[3]/td[1]/input', value=self.username)
                    self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[4]/td/input', value=self.password)
                    self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[5]/td[1]/input', value=vcode)
                    self.web.click(path='//*[@id="loginbt"]')
                except Exception as e:
                    logger.exception('Unable to input username/password/validation code.\n{}'.format(e))
                    self.renew()
                    continue

                if '验证码错误' in self.web.driver.page_source:
                    logger.info('Validation code is incorrect, try again.')
                    continue
                else:
                    try:
                        element = WebDriverWait(self.web.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, '/html/body/table/tbody/tr/td[1]'))
                        )
                    finally:
                        logger.info('Sucessfully login.')
                        return True
            else:
                self.renew()

    # Export excel with tax records
    def get(self, startdate=PRE3MONTH, enddate=TODAY, valid=''):
        logger.info('Query start date: {}, end date: {}, valid: {}'.format(str(startdate), str(enddate), str(valid)))
        tax_query = self.base +  'cxtj/getInvInfo.do?act=down&machineID=&type=&startDate={}&endDate={}&zfbz=&fpxz=&gfmc=&fpdm=&startFphm=&endFphm=&str_shuilv=0.04;0.06;0.10;0.09;0.11;0.13;0.16;0.17;0.03;0.05;0.015;9999&xsdjh=&bszt='.format(str(startdate), str(enddate))
        tax_detail_query = self.base + 'cxtj/getInvInfoMx.do?act=down&machineID=&type=&startDate={}&endDate={}&zfbz={}&fpxz=&gfmc=&fpdm=&startFphm=&endFphm=&spmc=&spgg=&str_shuilv=0.04;0.06;0.10;0.09;0.11;0.13;0.16;0.17;0.03;0.05;0.015;9999&xsdjh='.format(str(startdate), str(enddate), str(valid))
        tax_flag = self.download_file(tax_query, TAX_PATH)
        tax_detail_flag = self.download_file(tax_detail_query, TAX_DETAIL_PATH)
        return (tax_flag and tax_detail_flag)

    # Delete previous query file and download a new one
    def download_file(self, query, file_path):
        self.check_last_query(file_path)
        try:
            self.update_cookies()
            response = self.session.get(query)
            with open(file_path, 'wb') as writer:
                writer.write(response.content)
            logger.info('Download file {}.'.format(file_path))
            return True
        except Exception as e:
            logger.exception(e)
            return False

    # Check if file from previous exists, and delete it
    def check_last_query(self, path):
        if os.path.isfile(path):
            logger.info('Delete previous {}.'.format(path))
            os.remove(path)

    def update_cookies(self):
        self.cookies = self.web.get_requests_cookies()
        self.session.cookies.update(self.cookies)

    # Renew selenium and session
    # TODO: refresh selenium and session when error
    def renew(self):
        logger.info('Renew browser and session.')
        self.web.renew(self.base)
        self.web.driver.implicitly_wait(10)
        self.session = requests.session()
        self.cookies = requests.cookies.RequestsCookieJar()

    @classmethod
    def run(cls, entity, server, link, username, password, time=3600):
        t = cls(link, username, password)

        # Return false when function takes too much time
        def _timeout(func, timeout=time, **kwargs):
            try:
                result = func_timeout(timeout=timeout, func=func, kwargs=kwargs)
                return result
            except FunctionTimedOut as e:
                logger.error('Timeout:\n%s', e)
                return False

        while True:
            # Exit with error when login takes too much time
            if not _timeout(func=t.login):
                exit(1)
            success = t.get()
            if success:
                t.web.close()
                break
            else:
                logger.info('Restart job, Entity {} Server {}'.format(entity, server))
                t.renew()
                continue

        tax_df = pd.read_excel(TAX_PATH, sheet_name='发票信息', dtype=str)
        tax_df = tax_df[tax_df['序号'] != 'nan']
        tax_df['企业税号'] = entity
        tax_df['服务器号'] = server

        tax_detail_df = pd.read_excel(TAX_DETAIL_PATH, sheet_name='商品信息', dtype=str)
        tax_detail_df = tax_detail_df[tax_detail_df['序号'] != 'nan']
        tax_detail_df['企业税号'] = entity
        tax_detail_df['服务器号'] = server

        return tax_df, tax_detail_df


def _send_email(entity, receiver, attachment):
    # Send email
    scrapymail = em.Email()

    if (attachment is False) or attachment.empty:
        subject = '[PAM Tax Checking] - {} 发票无异常 {}'.format(TODAY, entity)
        content = 'Hi All,\r\n\r\n{}的发票无异常记录。\r\n\r\nThanks.'.format(entity)
        scrapymail.send(subject=subject, content=content, receivers=receiver, attachment=None)
    else:
        entity_path = ATTACHMENT_PATH.format(TODAY, entity)
        subject = '[PAM Tax Checking] - {} 发票异常清单 {}'.format(TODAY, entity)
        content = 'Hi All,\r\n\r\n请查看附件关于{}的发票异常记录。\r\n\r\nThanks.'.format(entity)
        attachment.to_excel(entity_path, index=False, header=True, sheet_name=entity)
        scrapymail.send(subject=subject, content=content, receivers=receiver, attachment=entity_path)
        logger.info('Delete attachment file.')
        os.remove(entity_path)

    scrapymail.close()


if __name__ == '__main__':

    logger.info('---------------   Irregular tax ratio query.   ---------------')

    with db.Mssql(keys.dbconfig) as scrapydb:
        access = scrapydb.select(ACCESS_TABLE_NAME)
        entities = '\'' + '\', \''.join(list(access['Entity_Name'])) + '\''
        logs = scrapydb.select(LOG_TABLE_NAME, source=SITE, customized={'Timestamp': ">='{}'".format(TODAY), 'City': 'IN ({})'.format(entities)})
        # Exclude entities with logs in same day. If no logs, refresh table
        if not logs.empty:
            logger.info('Exclude existing entities and continue.')
            access_run = access[-access['Entity_Name'].isin(logs['City'])]
        else:
            logger.info('Delete existing records and start a new query.')
            scrapydb.delete(table_name=TAX_TABLE)
            scrapydb.delete(table_name=TAX_DETAIL_TABLE)
            access_run = access

    # Core scraping process
    for index, row in access_run.iterrows():
        logger.info('---------------   Start new job. Entity: {} Server:{}    ---------------'.format(row['Entity_Name'], row['Server']))
        tax_df, tax_detail_df = timeout(func=Tax.run, time=3600, entity=row['Entity_Name'], server=row['Server'], link=row['Link'], username=row['User_Name'], password=row['Password'])
        # tax_df, tax_detail_df = Tax.run(entity=row['Entity_Name'], server=row['Server'], link=row['Link'], username=row['User_Name'], password=row['Password'])
        # Upload to database
        scrapydb = db.Mssql(keys.dbconfig)
        scrapydb.upload(df=tax_df, table_name=TAX_TABLE, new_id=False, dedup=False)
        scrapydb.upload(df=tax_detail_df, table_name=TAX_DETAIL_TABLE, new_id=False, dedup=False, start=PRE3MONTH, end=TODAY, timestamp=TIMESTAMP, source=SITE, city=row['Entity_Name'])
        scrapydb.close()

    # Ensure failure of scraping process do not interrupt email and sp execution
    with db.Mssql(keys.dbconfig) as scrapydb:
        # Update Irregular_Ind by executing stored procedure
        scrapydb.call_sp('CHN.Irregular_Tax_Refresh', table_name=TAX_DETAIL_TABLE, table_name2=TAX_TABLE)
        for index, row in access.iterrows():
            # Get irregular record
            att = scrapydb.call_sp(sp='CHN.Irregular_Tax_ETL', output=True, table_name=TAX_DETAIL_TABLE, entity_name=row['Entity_Name'])
            numeric_col = ['金额', '单价', '税率', '税额']

            if att is not False:
                att[numeric_col] = att[numeric_col].apply(pd.to_numeric)

            _send_email(entity=row['Entity_Name'], receiver=row['Email_List'], attachment=att)

    # Send email summary
    scrapyemail_summary = em.Email()
    scrapyemail_summary.send('[Scrapy]' + SITE, 'Done', LOG_PATH, receivers='benson.chen@ap.jll.com;helen.hu@ap.jll.com')
    scrapyemail_summary.close()
    exit(0)


