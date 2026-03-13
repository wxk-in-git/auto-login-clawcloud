# 文件名: login_script.py
# 作用: 自动登录 ClawCloud Run，支持 GitHub 账号密码 + 2FA 自动验证
import os
import time
import pyotp  # 用于生成 2FA 验证码
from playwright.sync_api import sync_playwright


def run_login():
    # 1. 获取环境变量中的敏感信息（建议优先用环境变量，避免硬编码）
    # 优先从环境变量读取，没有则使用硬编码值（仅用于测试）
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")

    if not username or not password:
        print("? 错误: 必须设置 GH_USERNAME 和 GH_PASSWORD 环境变量。")
        return

    print("? [Step 1] 启动浏览器...")
    with sync_playwright() as p:
        # 关键修改：headless=False 让浏览器前台显示
        # 添加 slow_mo 放慢操作速度，便于观察执行过程
        browser = p.chromium.launch(
            headless=False,  # 前台显示浏览器（核心修改）
            slow_mo=1000,  # 每个操作延迟1秒，方便查看
            args=[
                "--start-maximized",  # 浏览器最大化显示
                "--no-sandbox",  # 解决权限问题（部分系统需要）
            ]
        )
        # 设置浏览器上下文为最大化（配合上面的参数）
        context = browser.new_context(viewport=None)  # None 表示使用系统默认窗口大小
        page = context.new_page()

        # 2. 访问 ClawCloud 登录页
        target_url = "https://ap-northeast-1.run.claw.cloud/"
        print(f"? [Step 2] 正在访问: {target_url}")
        page.goto(target_url)
        page.wait_for_load_state("networkidle", timeout=20000)
        time.sleep(10)

        # 3. 点击 GitHub 登录按钮
        print("? [Step 3] 寻找 GitHub 按钮...")
        try:
            # 精确查找包含 'GitHub' 文本的按钮
            login_button = page.locator("button:has-text('GitHub')")
            login_button.wait_for(state="visible", timeout=10000)
            time.sleep(10)
            login_button.click()
            print("? 按钮已点击")
        except Exception as e:
            print(f"?? 未找到 GitHub 按钮 (可能已自动登录或页面变动): {e}")

        # 4. 处理 GitHub 登录表单
        print("? [Step 4] 等待跳转到 GitHub...")
        try:
            # 等待 URL 变更为 github.com
            page.wait_for_url(lambda url: "github.com" in url, timeout=30000)
            time.sleep(10)
            
            # 如果是在登录页，则填写账号密码
            if "login" in page.url:
                print("? 输入账号密码...")
                page.fill("#login_field", username)
                page.fill("#password", password)
                page.click("input[name='commit']")  # 点击登录按钮
                time.sleep(10)
                print("? 登录表单已提交")
        except Exception as e:
            print(f"?? 跳过账号密码填写 (可能已自动登录): {e}")

        # 5. 【核心】处理 2FA 双重验证 (解决异地登录拦截)
        page.wait_for_timeout(3000)
        time.sleep(10)

        # 检查 URL 是否包含 two-factor 或页面是否有验证码输入框
        if "two-factor" in page.url or page.locator("#app_totp").count() > 0:
            print("? [Step 5] 检测到 2FA 双重验证请求！")

            if totp_secret:
                print("? 正在计算动态验证码 (TOTP)...")
                try:
                    # 使用密钥生成当前的 6 位验证码
                    totp = pyotp.TOTP(totp_secret)
                    token = totp.now()
                    print(f"   ? 生成的验证码: {token}")

                    # 填入 GitHub 的验证码输入框 (ID 通常是 app_totp)
                    page.fill("#app_totp", token)
                    # 手动点击验证按钮（增加可靠性）
                    page.click("button[type='submit']")
                    print("? 验证码已提交，等待跳转...")
                except Exception as e:
                    print(f"? 填入验证码失败: {e}")
            else:
                print("? 致命错误: 检测到 2FA 但未配置 GH_2FA_SECRET！")
                exit(1)

        # 6. 处理授权确认页 (Authorize App)
        page.wait_for_timeout(3000)
        if "authorize" in page.url.lower():
            print("? 检测到授权请求，尝试点击 Authorize...")
            try:
                authorize_btn = page.locator("button:has-text('Authorize')").first
                authorize_btn.wait_for(state="visible", timeout=5000)
                authorize_btn.click()
                print("? 授权按钮已点击")
            except Exception as e:
                print(f"?? 授权按钮点击失败: {e}")

        # 7. 等待最终跳转结果
        print("? [Step 6] 等待跳转回 ClawCloud 控制台 (约20秒)...")
        page.wait_for_timeout(20000)

        final_url = page.url
        print(f"? 最终页面 URL: {final_url}")

        # 截图保存，用于查看结果
        page.screenshot(path="login_result.png")
        print("? 已保存结果截图: login_result.png")

        # 8. 验证是否成功
        is_success = False

        # 多维度检查登录成功状态
        success_indicators = [
            page.get_by_text("App Launchpad").count() > 0,
            page.get_by_text("Devbox").count() > 0,
            "private-team" in final_url,
            "console" in final_url,
            "signin" not in final_url and "github.com" not in final_url
        ]

        if any(success_indicators):
            is_success = True

        if is_success:
            print("? 登录成功！任务完成。")
            # 保持浏览器打开（方便查看结果），按任意键关闭
            input("按 Enter 键关闭浏览器...")
        else:
            print("? 登录失败。请查看 login_result.png 或浏览器页面排查原因。")
            input("按 Enter 键关闭浏览器...")
            exit(1)

        browser.close()


if __name__ == "__main__":
    run_login()
