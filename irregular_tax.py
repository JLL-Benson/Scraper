"""
Created on Thur May 11th 2019

@author: Benson.Chen benson.chen@ap.jll.com
"""


import keys
import re
import pandas as pd
import db
import pagemanipulate as pm
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
import baidu_api
import requests
import time
import utility_email as em
from utility_commons import *


SCREENSHOT_PATH = PIC_DIR + r'\screen_shot.jpg'
VCODE_PATH = PIC_DIR + r'\vcode.jpg'
FILE_PATH = FILE_DIR + r'\Irregular_Tax.xls'
ATTACHMENT_PATH = FILE_DIR + r'\{}_异常发票清单_{}.xlsx'
TABLE_NAME = 'Scrapy_Irregular_TAX'


class Tax:

    def __init__(self, link, username, password):

        self.base = link
        # self.site = site
        # self.server = server
        self.username = username
        self.password = password
        self.web = pm.Page(self.base, 'normal')
        self.web.driver.implicitly_wait(10)
        self.session = requests.session()
        self.cookies = requests.cookies.RequestsCookieJar()

    # Crop validation code pic from screen shot
    def get_vcode_pic(self):
        self.web.driver.save_screenshot(SCREENSHOT_PATH)
        pic = self.web.driver.find_element_by_xpath('//*[@id="crcpic"]')
        vcode_pic = Image.open(SCREENSHOT_PATH)
        # im.save(r'C:/Users/Benson.Chen/Desktop/Scraper/code0.jpg')
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

        while True:
            vpic = self.get_vcode_pic()
            bd = baidu_api.Baidu(api='ocr')
            ocr_result = bd.ocr_api_call(vpic, VCODE_PATH, bin_threshold=100, detect_direction='false', language_type='ENG', probability='true')
            vcode = self.vcode_validate(ocr_result)
            if vcode:
                logging.info('Get validation code "{}". Try to login.'.format(vcode))
                return vcode
            else:
                # logging.info('Cannot recognize validation code, try again.')
                self.web.driver.find_element_by_xpath('//*[@id="crcpic"]').click()

    # Login
    def login(self, username, password):
        while True:
            vcode = self.get_vcode()
            self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[3]/td[1]/input', value=username)
            self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[4]/td/input', value=password)
            self.web.send(path='//*[@id="login"]/tbody/tr/td/table/tbody/tr[5]/td[1]/input', value=vcode)
            self.web.click(path='//*[@id="loginbt"]')
            if '验证码错误' in self.web.driver.page_source:
                logging.info('Validation code is incorrect, try again.')
                continue
            else:
                try:
                    element = WebDriverWait(self.web.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, '/html/body/table/tbody/tr/td[1]'))
                    )
                finally:
                    logging.info('Sucessfully login.')
                    break

    # Export excel with tax records
    def get(self, startdate=PRE3MONTH, enddate=TIMESTAMP, valid=''):
        logging.info('Query start date: {}, end date: {}, valid: {}'.format(str(startdate), str(enddate), str(valid)))
        query = self.base + 'cxtj/getInvInfoMx.do?act=down&machineID=&type=&startDate={}&endDate={}&zfbz={}&fpxz=&gfmc=&fpdm=&startFphm=&endFphm=&spmc=&spgg=&str_shuilv=0.04;0.06;0.10;0.09;0.11;0.13;0.16;0.17;0.03;0.05;0.015;9999&xsdjh='.format(str(startdate), str(enddate), str(valid))
        self.check_last_query()
        try:
            # self.web.driver.get(query1)
            # self.web.click(path='//*[@id="tip"]/table/tbody/tr[6]/td/input')
            self.update_cookies()
            response = self.session.get(query)
            with open(FILE_PATH, 'wb') as writer:
                writer.write(response.content)
            logging.info('Download file.')
            return True
        except Exception as e:
            logging.error(e)
            return False

    # Check if file from previous exists, and delete it
    def check_last_query(self):
        if os.path.isfile(FILE_PATH):
            logging.info('Delete previous query result')
            os.remove(FILE_PATH)

    def update_cookies(self):
        self.cookies = self.web.get_requests_cookies()
        self.session.cookies.update(self.cookies)

    @classmethod
    def run(cls, site, server, link, username, password):
        while True:
            t = cls(link, username, password)
            t.login(username=username, password=password)
            success = t.get()
            t.web.close()
            if success:
                break
            else:
                logging.info('Restart job, Entity {} Server {}'.format(site, server))
                continue
        tax_df = pd.read_excel(FILE_PATH, sheet_name='商品信息', dtype=str)
        tax_df = tax_df[tax_df['序号'] != 'nan']
        tax_df['企业税号'] = site
        tax_df['服务器号'] = server

        return tax_df


if __name__ == '__main__':

    with db.Mssql(keys.dbconfig) as scrapydb, em.Email() as scrapymail:

        access = scrapydb.select(TABLE_NAME + '_Access')
        irregular_ind = "case when left([商品名称],charindex('*',[商品名称],charindex('*',[商品名称])+1)) in (N'*印刷品*',N'*计算机配套产品*',N'*劳务*',N'*供电*') and [税率] <> 0.13 " \
                    "or left([商品名称],charindex('*',[商品名称],charindex('*',[商品名称])+1)) in (N'*企业管理服务*')                                  and [税率] <> 0.06 " \
                    "or left([商品名称],charindex('*',[商品名称],charindex('*',[商品名称])+1)) in (N'*燃气*')                                         and [税率] <> 0.09 " \
                    "then 'Y' " \
                    "when left([商品名称],charindex('*',[商品名称],charindex('*',[商品名称])+1)) in (N'*水冰雪*') " \
                    "then case when [企业税号] = '91440300791704433Q' and [税率] <> 0.03 then 'Y' " \
                    "when [企业税号] <>'91440300791704433Q' and [税率] <> 0.09 then 'Y' " \
                    "else 'N' " \
                    "end " \
                    "else 'N' " \
                    "end"
        logging.info('---------------   Irregular tax ratio query.   ---------------')
        logging.info('Delete existing records.')
        scrapydb.delete(TABLE_NAME)

        for index, row in access.iterrows():
            logging.info('---------------   Start new job. Entity: {} Server:{}    ---------------'.format(row['Entity_Name'], row['Server']))
            result = Tax.run(site=row['Entity_Name'], server=row['Server'], link=row['Link'], username=row['User_Name'], password=row['Password'])

            # Upload to database
            scrapydb.upload(result, TABLE_NAME, False, False, None, start=PRE3MONTH, end=TODAY,  timestamp=TIMESTAMP)

            # Update Irregular_Ind
            scrapydb.update(TABLE_NAME, 'Irregular_Ind', irregular_ind, False, **{'企业税号': row['Entity_Name']})
            # Get irregular record
            att = scrapydb.select(TABLE_NAME, '*', **{'企业税号': row['Entity_Name'], 'Irregular_Ind': 'Y', '作废标志': '否'})

            # Send email
            subject = '[PAM Tax Checking] - {} ---发票异常清单--- {}'.format(row['Entity_Name'], TODAY)
            content = 'Hi All,\r\n请查看附件关于{}的发票异常记录。\r\n\r\nThanks.'.format(row['Entity_Name'])
            if not att.empty:
                att.to_excel(ATTACHMENT_PATH.format(TODAY, row['Entity_Name']), index=False, header=True, sheet_name=row['Entity_Name'])
                scrapymail.send(subject=subject, content=content, receivers=row['Email_List'], attachment=ATTACHMENT_PATH.format(TODAY, row['Entity_Name']))
            else:
                scrapymail.send(subject=subject, content=content, receivers=row['Email_List'], attachment=None)

            time.sleep(20)

