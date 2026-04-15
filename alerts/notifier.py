"""
告警推送模块
"""

import json
import requests
from typing import Dict, Optional
from config import get_config


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self.config = get_config()
        self.alert_config = self.config.alert_config

    def check_and_send(self, panic_index: float, status: str, date: str) -> bool:
        """
        检查告警条件并发送

        Returns:
            是否发送了告警
        """
        if not self.alert_config.get("enabled", False):
            return False

        rules = self.alert_config.get("rules", {})

        for rule_name, rule in rules.items():
            if self._should_alert(panic_index, rule.get("condition", "")):
                message = rule.get("message", "").format(index=f"{panic_index:.1f}")
                self._send_alert(message, rule.get("priority", "medium"), date)
                return True

        return False

    def _should_alert(self, panic_index: float, condition: str) -> bool:
        """检查是否满足告警条件"""
        try:
            # 简单解析条件，如 ">= 80"
            condition = condition.strip()
            if condition.startswith(">="):
                return panic_index >= float(condition[2:])
            elif condition.startswith("<="):
                return panic_index <= float(condition[2:])
            elif condition.startswith(">"):
                return panic_index > float(condition[1:])
            elif condition.startswith("<"):
                return panic_index < float(condition[1:])
            return False
        except:
            return False

    def _send_alert(self, message: str, priority: str, date: str):
        """发送告警"""
        # 飞书推送
        if self.alert_config.get("feishu", {}).get("enabled"):
            self._send_feishu(message, priority, date)

        # 微信推送
        if self.alert_config.get("weixin", {}).get("enabled"):
            self._send_weixin(message, priority, date)

        # 邮件推送
        if self.alert_config.get("email", {}).get("enabled"):
            self._send_email(message, priority, date)

    def _send_feishu(self, message: str, priority: str, date: str):
        """发送到飞书"""
        try:
            feishu_config = self.alert_config.get("feishu", {})
            webhook_url = feishu_config.get("webhook_url", "")

            if not webhook_url:
                print("  ⚠️ 飞书webhook未配置")
                return

            # 构建消息
            color_map = {"high": "red", "medium": "orange", "low": "blue"}

            payload = {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": "📊 A股恐慌指数告警"},
                        "template": color_map.get(priority, "blue"),
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**日期**: {date}\n\n{message}",
                            },
                        }
                    ],
                },
            }

            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"  ✅ 飞书告警已发送")
            else:
                print(f"  ⚠️ 飞书告警发送失败: {response.text}")

        except Exception as e:
            print(f"  ⚠️ 飞书告警发送失败: {e}")

    def _send_weixin(self, message: str, priority: str, date: str):
        """发送到微信"""
        try:
            weixin_config = self.alert_config.get("weixin", {})
            user_id = weixin_config.get("user_id", "")

            if not user_id:
                print("  ⚠️ 微信用户ID未配置")
                return

            # 通过微信API发送（需要外部实现）
            print(f"  📱 微信告警: {message}")

        except Exception as e:
            print(f"  ⚠️ 微信告警发送失败: {e}")

    def _send_email(self, message: str, priority: str, date: str):
        """发送到邮件"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            email_config = self.alert_config.get("email", {})
            smtp_server = email_config.get("smtp_server", "")
            smtp_port = email_config.get("smtp_port", 587)
            smtp_user = email_config.get("smtp_user", "")
            smtp_password = email_config.get("smtp_password", "")
            to_email = email_config.get("to_email", "")
            
            if not all([smtp_server, smtp_user, smtp_password, to_email]):
                print("  ⚠️ 邮件配置不完整")
                return
            
            # 构建邮件
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to_email
            msg['Subject'] = f"📊 A股恐慌指数告警 - {date}"
            
            body = f"""日期: {date}

{message}

此邮件由A股恐慌指数系统自动发送，请勿回复。"""
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            print(f"  ✅ 邮件告警已发送")
            
        except Exception as e:
            print(f"  ⚠️ 邮件告警发送失败: {e}")

    def generate_daily_report(self, data: Dict) -> str:
        """生成每日报告"""
        report = f"""📊 A股恐慌指数日报 ({data.get('date', '')})

━━━━━━━━━━━━━━━━━━━━
📈 核心指标
━━━━━━━━━━━━━━━━━━━━
恐慌指数: {data.get('panic_index', 0):.2f} ({data.get('status', '未知')})
波动率: {data.get('volatility', 0)*100:.2f}%
涨跌停比: {data.get('limit_ratio', 0)*100:.1f}%

━━━━━━━━━━━━━━━━━━━━
💡 操作建议
━━━━━━━━━━━━━━━━━━━━
{data.get('signal', {}).get('reason', '无建议')}

━━━━━━━━━━━━━━━━━━━━
📊 历史对比
━━━━━━━━━━━━━━━━━━━━
7日平均: {data.get('avg_7d', 0):.2f}
30日平均: {data.get('avg_30d', 0):.2f}
"""
        return report
