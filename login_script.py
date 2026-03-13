# 文件名: login_script.py
# 作用: 自动登录 ClawCloud Run，支持 GitHub 账号密码 + 2FA 自动验证

import os
import time
import pyotp  # 用于生成 2FA 验证码
from playwright.sync_api import sync_playwright

def run_login():
    # 1. 获取环境变量中的敏感信息
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")

    if not username or not password:
        print("❌ 错误: 必须设置 GH_USERNAME 和 GH_PASSWORD 环境变量。")
        return

    print("🚀 [Step 1] 启动浏览器...")
    with sync_playwright() as p:
        # 启动浏览器 (headless=True 表示无头模式，适合服务器运行)
        browser = p.chromium.launch(headless=True)
        # 设置大一点的分辨率，避免页面布局错乱
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        # 2. 访问 ClawCloud 登录页
        target_url = "https://ap-northeast-1.run.claw.cloud/"
        print(f"🌐 [Step 2] 正在访问: {target_url}")
        page.goto(target_url)
        page.wait_for_load_state("networkidle")

        # 3. 点击 GitHub 登录按钮
        print("🔍 [Step 3] 寻找 GitHub 按钮...")
        try:
            # 精确查找包含 'GitHub' 文本的按钮
            login_button = page.locator("button:has-text('GitHub')")
            login_button.wait_for(state="visible", timeout=30000)
            login_button.click()
            print("✅ 按钮已点击")
        except Exception as e:
            print(f"⚠️ 未找到 GitHub 按钮 (可能已自动登录或页面变动): {e}")
            # 精确查找包含 'GitHub' 文本的按钮
            login_button = page.locator("button:has-text('GitHub')")
            login_button.wait_for(state="visible", timeout=30000)
            login_button.click()
            print("✅ 按钮再次点击")
        # 4. 处理 GitHub 登录表单
        print("⏳ [Step 4] 等待跳转到 GitHub...")
        try:
            # 精确查找包含 'GitHub' 文本的按钮
            login_button = page.locator("button:has-text('GitHub')")
            login_button.wait_for(state="visible", timeout=30000)
            login_button.click()
            print("✅ 按钮再次点击1")            
            # 等待 URL 变更为 github.com
            page.wait_for_url(lambda url: "github.com" in url, timeout=30000)
            time.sleep(10)

            # 如果是在登录页，则填写账号密码
            if "login" in page.url:
                print("🔒 输入账号密码...")
                page.fill("#login_field", username)
                page.fill("#password", password)
                page.click("input[name='commit']") # 点击登录按钮
                print("📤 登录表单已提交")
        except Exception as e:
            print(f"ℹ️ 跳过账号密码填写 (可能已自动登录): {e}")

        # 5. 【核心】处理 2FA 双重验证 (解决异地登录拦截)
        # 给页面一点时间跳转
        page.wait_for_timeout(3000)
        
        # 检查 URL 是否包含 two-factor 或页面是否有验证码输入框
        if "two-factor" in page.url or page.locator("#app_totp").count() > 0:
            print("🔐 [Step 5] 检测到 2FA 双重验证请求！")
            
            if totp_secret:
                print("🔢 正在计算动态验证码 (TOTP)...")
                try:
                    # 使用密钥生成当前的 6 位验证码
                    totp = pyotp.TOTP(totp_secret)
                    token = totp.now()
                    print(f"   生成的验证码: {token}")
                    
                    # 填入 GitHub 的验证码输入框 (ID 通常是 app_totp)
                    page.fill("#app_totp", token)
                    print("✅ 验证码已填入，GitHub 应会自动跳转...")
                    
                    # 某些情况下可能需要手动回车，这里做个保险
                    # page.keyboard.press("Enter")
                except Exception as e:
                    print(f"❌ 填入验证码失败: {e}")
            else:
                print("❌ 致命错误: 检测到 2FA 但未配置 GH_2FA_SECRET Secret！")
                exit(1)

        # 6. 处理授权确认页 (Authorize App)
        # 第一次登录可能会出现
        page.wait_for_timeout(5000)
        if "authorize" in page.url.lower():
            print("⚠️ 检测到授权请求，尝试点击 Authorize...")
            try:
                page.click("button:has-text('Authorize')", timeout=5000)
            except:
                pass

        # 7. 等待最终跳转结果
        print("⏳ [Step 6] 等待跳转回 ClawCloud 控制台 (约20秒)...")
        # 强制等待较长时间，确保页面完全重定向
        page.wait_for_timeout(30000)
        
        final_url = page.url
        print(f"📍 最终页面 URL: {final_url}")
        
        # 截图保存，用于 GitHub Actions 查看结果
        page.screenshot(path="login_result.png")
        print("📸 已保存结果截图: login_result.png")

        # 8. 验证是否成功
        # 成功的标志：URL 不再是 GitHub，且包含控制台特征
        is_success = False
        
        # 检查点 A: 页面包含特定文字 (最准确)
        if page.get_by_text("App Launchpad").count() > 0 or page.get_by_text("Devbox").count() > 0:
            is_success = True
        # 检查点 B: URL 包含 console 特征
        elif "private-team" in final_url or "console" in final_url:
            is_success = True
        # 检查点 C: 只要不是登录页也不是 GitHub 验证页
        elif "signin" not in final_url and "github.com" not in final_url:
            is_success = True

        if is_success:
            print("🎉🎉🎉 登录成功！任务完成。")
        else:
            print("😭😭😭 登录失败。请下载 login_result.png 查看原因。")
            exit(1) # 抛出错误代码，让 Action 变红

        browser.close()

if __name__ == "__main__":
    run_login()
