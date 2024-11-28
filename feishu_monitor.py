from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import requests
import json
import logging
import threading

class FeishuMonitor:
    def __init__(self, source_group, webhook_url):
        self.source_group = source_group
        self.webhook_url = webhook_url
        self.driver = None
        self.logger = self.setup_logger()
        self.processed_messages = set()  # 用于存储已处理的消息ID

    def setup_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def setup_driver(self):
        chrome_options = Options()
        # chrome_options.add_argument('--headless')  # 无头模式，如果需要看到浏览器界面可以注释掉这行
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)

    def login(self):
        try:
            self.driver.get("https://www.feishu.cn/messenger/")
            self.logger.info("等待扫码登录...")
            
            # 等待头像元素出现来确认登录成功
            wait = WebDriverWait(self.driver, 300)
            avatar_loaded = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ud__avatar__image"))
            )
            
            if avatar_loaded:
                self.logger.info("检测到头像元素，登录成功！")
                time.sleep(3)  # 给页面一些加载时间
                return True
                
        except Exception as e:
            self.logger.error(f"登录失败: {str(e)}")
            return False

    def print_page_elements(self):
        """打印页面上所有可见元素的信息"""
        try:
            self.logger.info("开始获取页面元素信息...")
            # 获取所有元素
            elements = self.driver.find_elements(By.CSS_SELECTOR, "*")
            
            for element in elements:
                try:
                    # 获取元素的各种属性
                    tag_name = element.tag_name
                    class_name = element.get_attribute("class")
                    element_id = element.get_attribute("id")
                    text = element.text.strip()
                    
                    if text or class_name or element_id:  # 只打印有意义的元素
                        element_info = f"""
                        标签: {tag_name}
                        类名: {class_name}
                        ID: {element_id}
                        文本: {text}
                        {'='*50}
                        """
                        self.logger.info(element_info)
                except Exception as e:
                    continue
                    
        except Exception as e:
            self.logger.error(f"获取页面元素时发生错误: {str(e)}")

    def search_group(self):
        try:
            self.logger.info(f"开始搜索目标群组: {self.source_group}")
            
            # 模拟按下 Command + K
            actions = ActionChains(self.driver)
            actions.key_down(Keys.COMMAND).send_keys('k').key_up(Keys.COMMAND).perform()
            time.sleep(2)  # 等待搜索框出现
            
            # 尝试找到并点击搜索框
            try:
                # 等待搜索框出现
                wait = WebDriverWait(self.driver, 10)
                search_container = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-base-editor"))
                )
                self.logger.info("找到搜索框")
                
                # 点击搜索框使其获得焦点
                search_container.click()
                time.sleep(1)
                
                # 直接输入文字
                actions = ActionChains(self.driver)
                for char in self.source_group:
                    actions.send_keys(char)
                actions.perform()
                
                self.logger.info(f"在搜索框中输入: {self.source_group}")
                time.sleep(2)  # 等待搜索结果
                
            except Exception as e:
                self.logger.error(f"输入搜索文本失败: {str(e)}")
                return False
            
            # 等待并查找群组卡片
            try:
                wait = WebDriverWait(self.driver, 10)
                
                # 使用更精确的选择器定位整个群组卡片
                group_card_xpath = "//div[contains(@class, 'group-chat-card')]//span[contains(@class, 'highlight-tag') and contains(text(), '{}')]/ancestor::div[contains(@class, 'group-chat-card')]".format(self.source_group)
                
                group_card = wait.until(
                    EC.presence_of_element_located((By.XPATH, group_card_xpath))
                )
                
                self.logger.info("找到目标群组卡片")
                
                # 确保元素可点击
                wait.until(EC.element_to_be_clickable((By.XPATH, group_card_xpath)))
                
                # 使用JavaScript滚动到元素位置
                self.driver.execute_script("arguments[0].scrollIntoView(true);", group_card)
                time.sleep(1)  # 等待滚动完成
                
                # 先尝试直接点击
                try:
                    group_card.click()
                except:
                    # 如果直接点击失败，使用JavaScript点击
                    self.driver.execute_script("arguments[0].click();", group_card)
                
                self.logger.info("已点击目标群组")
                time.sleep(2)  # 等待群组加载
                
                return True
                
            except Exception as e:
                self.logger.error(f"查找群组卡片时发生错误: {str(e)}")
                return False
            
        except Exception as e:
            self.logger.error(f"搜索群组时发生错误: {str(e)}")
            return False

    def find_target_group(self):
        # 直接使用搜索功能查找群组
        return self.search_group()

    def get_latest_messages(self):
        try:
            wait = WebDriverWait(self.driver, 10)
            
            # 等待消息加载
            messages = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.NewMessageContextMenuTrigger"))
            )
            
            # 反转消息列表，使最新的消息在前面
            messages.reverse()
            
            self.logger.info(f"找到 {len(messages)} 条消息")
            
            # 获取最新的消息
            latest_messages = []
            processed_contents = set()  # 用于检查消息内容是否重复
            
            for message in messages[:10]:  # 获取最新的10条消息
                try:
                    message_id = message.get_attribute('id')
                    
                    # 获取所有text-only span元素
                    text_spans = message.find_elements(By.CSS_SELECTOR, "span.text-only")
                    if not text_spans:
                        continue
                        
                    # 组合所有文本内容
                    message_text = '\n'.join([span.text for span in text_spans if span.text.strip()])
                    if not message_text:  # 如果消息为空，跳过
                        continue
                        
                    # 检查消息内容是否重复
                    if message_text in processed_contents:
                        self.logger.info(f"跳过重复消息: {message_text[:100]}...")
                        continue
                        
                    # 获取所有链接
                    links = message.find_elements(By.CSS_SELECTOR, "a.rich-text-anchor")
                    urls = [link.get_attribute('href') for link in links]
                    
                    # 添加到待处理消息列表
                    message_info = {
                        'id': message_id,
                        'content': message_text,
                        'links': urls
                    }
                    
                    latest_messages.append(message_info)
                    processed_contents.add(message_text)  # 记录已处理的消息内容
                    self.logger.info(f"发现新消息:\n{message_text}")
                
                except Exception as e:
                    self.logger.error(f"提取消息内容时发生错误: {str(e)}")
                    continue
            
            return latest_messages
            
        except Exception as e:
            self.logger.error(f"获取消息时发生错误: {str(e)}")
            return []

    def forward_message(self, message):
        try:
            # 构建要发送的消息
            formatted_message = message['content']
            if message['links']:
                formatted_message += "\n\n相关链接:\n"
                for link in message['links']:
                    formatted_message += f"{link}\n"
            
            # 发送到webhook
            payload = {
                "msg_type": "text",
                "content": {
                    "text": formatted_message
                }
            }
            
            response = requests.post(self.webhook_url, json=payload)
            if response.status_code == 200:
                self.logger.info(f"消息转发成功: {message['id']}")
                return True
            else:
                self.logger.error(f"消息转发失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"转发消息时发生错误: {str(e)}")
            return False

    def monitor_and_forward(self):
        try:
            self.setup_driver()
            if not self.login():
                self.logger.error("登录失败")
                return
                
            if not self.search_group():
                self.logger.error("找不到目标群组")
                return
                
            self.logger.info("开始监控消息")
            
            last_content = None  # 记录最后一条消息的内容
            
            # 直接开始监控消息
            while True:
                try:
                    messages = self.get_latest_messages()
                    if messages:
                        # 只处理最新的且不重复的消息
                        for message in messages:
                            if message['content'] != last_content:
                                success = self.forward_message(message)
                                if success:
                                    self.logger.info("消息转发成功")
                                    last_content = message['content']  # 更新最后转发的消息内容
                                else:
                                    self.logger.error("消息转发失败")
                            else:
                                self.logger.info("跳过重复消息")
                    
                    time.sleep(2)
                    
                except Exception as e:
                    self.logger.error(f"监控循环中发生错误: {str(e)}")
                    time.sleep(5)
                    
        except Exception as e:
            self.logger.error(f"监控过程中发生错误: {str(e)}")
        finally:
            if self.driver:
                self.driver.quit()

def run_monitor(config):
    try:
        print(f"开始监控群组: {config['source_group']}")
        monitor = FeishuMonitor(config["source_group"], config["webhook_url"])
        monitor.monitor_and_forward()
    except Exception as e:
        print(f"监控 {config['source_group']} 时发生错误: {str(e)}")

if __name__ == "__main__":
    print("启动飞书监控脚本...")
    print("按 Ctrl+C 可以随时停止脚本")
    print("-" * 50)
    
    # 配置多个监控实例
    configs = [
        {
            "source_group": "铭文符文mint监控群",
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/c34fc84c-1862-4172-8897-f1f143316ec4"
        },
        {
            "source_group": "聪明钱监控",
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/a410a5e0-9194-47b4-af8e-8da754d5d4bb"
        },
    ]
    
    # 使用多线程运行多个监控实例
    import threading
    
    threads = []
    try:
        # 为每个配置创建一个线程
        for config in configs:
            thread = threading.Thread(target=run_monitor, args=(config,))
            threads.append(thread)
            thread.start()
            print(f"已启动监控线程: {config['source_group']}")
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
    except KeyboardInterrupt:
        print("\n检测到 Ctrl+C，正在退出程序...")
    except Exception as e:
        print(f"程序发生错误: {str(e)}")
    finally:
        print("程序已退出")
