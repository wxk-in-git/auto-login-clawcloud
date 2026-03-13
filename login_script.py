# 文件名: login_script.py
# 新增：统计页面数量 + 给每个页面单独截图
import os
import sys
import time
import pyotp
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# 封装增强版截图函数（支持多页面截图+页面数统计）
def take_enhanced_screenshot(context, step_name, screenshot_dir="screenshots"):
    """
    生成步骤截图（包含页面数量统计+每个页面单独截图）
    :param context: playwright的browser_context对象（用于获取所有页面）
    :param step_name: 步骤名称（用于文件名）
    :param screenshot_dir: 截图保存目录
    """
    # 创建截图目录
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    
    # 1. 统计当前页面数量
    pages = context.pages
    page_count = len(pages)
    print(f"📊 [{step_name}] 当前浏览器页面数量: {page_count}")
    
    # 2. 记录页面数量到日志文件
    with open(f"{screenshot_dir}/page_count_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 步骤: {step_name} | 页面数量: {page_count}\n")
    
    # 3. 给每个页面单独截图
    for idx, page in enumerate(pages):
        try:
            # 页面截图命名：步骤_页面序号_时间戳.png
            filename = f"{screenshot_dir}/step_{step_name.replace(' ', '_')}_page_{idx+1}_{int(time.time())}.png"
            page.screenshot(path=filename, full_page=True)
            print(f"📸 [{step_name}] 页面{idx+1}截图已保存: {filename}")
        except Exception as e:
            print(f"⚠️ [{step_name}] 页面{idx+1}截图失败: {str(e)}")
            # 记录失败信息到日志
            with open(f"{screenshot_dir}/page_count_log.txt", "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 步骤: {step_name} | 页面{idx+1}截图失败: {str(e)}\n")
    
    # 4. 生成当前步骤的汇总截图（所有页面信息）
    summary_filename = f"{screenshot_dir}/step_{step_name.replace(' ', '_')}_summary_{int(time.time())}.txt"
    with open(summary_filename, "w", encoding="utf-8") as f:
        f.write(f"步骤: {step_name}\n")
        f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"页面总数: {page_count}\n")
        for idx, page in enumerate(pages):
            f.write(f"页面{idx+1} URL: {page.url}\n")
            f.write(f"页面{idx+1} 标题: {page.title()}\n")
            f.write("---\n")
    print(f"📝 [{step_name}] 页面汇总信息已保存: {summary_filename}")


def run_login():
    # 初始化环境变量检查
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")

    if not username or not password:
        print("❌ 错误: 必须设置 GH_USERNAME 和 GH_PASSWORD 环境变量。")
        # 即使环境变量缺失，也创建日志记录
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
        with open("screenshots/error_log.txt", "w", encoding="utf-8") as f:
            f.write(f"环境变量缺失 - GH_USERNAME: {username}, GH_PASSWORD: {password}\n")
        return

    print("✅ [Step 1] 启动浏览器...")
    with sync_playwright() as p:
        is_ci_env = os.environ.get("CI") == "true" or not sys.stdout.isatty()
        browser = p.chromium.launch(
            headless=is_ci_env,
            slow_mo=500,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(viewport=None)
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """)
        page = context.new_page()

        # Step1: 浏览器启动后 - 统计页面数+截图
        take_enhanced_screenshot(context, "浏览器启动完成")

        # 2. 访问ClawCloud登录页
        target_url = "https://ap-northeast-1.run.claw.cloud/"
        print(f"✅ [Step 2] 正在访问: {target_url}")
        try:
            page.goto(target_url, timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=20000)
            print("✅ 页面加载完成")
            time.sleep(20)
            # Step2: 登录页加载后 - 统计页面数+截图
            take_enhanced_screenshot(context, "ClawCloud登录页加载完成")
        except PlaywrightTimeoutError:
            print("❌ 页面加载超时！")
            take_enhanced_screenshot(context, "ClawCloud登录页加载超时")
            browser.close()
            return

        # 3. 点击GitHub登录按钮
        print("✅ [Step 3] 寻找 GitHub 登录按钮...")
        github_button = None
        locator_strategies = [
            "button:has-text('GitHub')",
            "a:has-text('GitHub')",
            "[data-provider='github']",
            "[href*='github']",
            "//button[contains(text(), 'GitHub')]",
            "//a[contains(text(), 'GitHub')]"
        ]

        for locator_str in locator_strategies:
            try:
                temp_locator = page.locator(locator_str)
                if temp_locator.count() > 0 and temp_locator.is_visible(timeout=2000):
                    github_button = temp_locator
                    print(f"✅ 找到 GitHub 按钮 (定位策略: {locator_str})")
                    break
            except:
                continue

        # Step3: 查找GitHub按钮后 - 统计页面数+截图
        take_enhanced_screenshot(context, "查找GitHub按钮后")

        if not github_button:
            print("❌ 未找到 GitHub 登录按钮！")
            browser.close()
            return

        # 点击GitHub按钮
        try:
            github_button.scroll_into_view_if_needed()
            time.sleep(1)
            github_button.click(force=True, timeout=5000)
            print("✅ GitHub 按钮点击成功（常规点击）")
            # Step3: 点击GitHub按钮后 - 统计页面数+截图
            take_enhanced_screenshot(context, "GitHub按钮点击成功")
        except:
            try:
                page.evaluate("(element) => element.click()", github_button.element_handle())
                print("✅ GitHub 按钮点击成功（JS点击）")
                take_enhanced_screenshot(context, "GitHub按钮点击成功_JS方式")
            except Exception as e:
                print(f"❌ GitHub 按钮点击失败: {str(e)}")
                take_enhanced_screenshot(context, "GitHub按钮点击失败")
                browser.close()
                return

        # 4. 处理GitHub登录表单
        print("✅ [Step 4] 等待跳转到 GitHub 登录页...")
        try:
            page.wait_for_url(lambda url: "github.com" in url, timeout=30000)
            print(f"✅ 已跳转到: {page.url}")
            time.sleep(20)
            # Step4: 跳转到GitHub后 - 统计页面数+截图
            take_enhanced_screenshot(context, "跳转到GitHub页面")

            if "login" in page.url.lower():
                print("✅ 开始填写 GitHub 账号密码...")
                if page.locator("#login_field").is_visible(timeout=5000):
                    page.fill("#login_field", username)
                    print("✅ 账号填写完成")
                    take_enhanced_screenshot(context, "GitHub账号填写完成")
                else:
                    print("❌ 未找到账号输入框")
                    take_enhanced_screenshot(context, "未找到GitHub账号输入框")
                    browser.close()
                    return

                if page.locator("#password").is_visible(timeout=5000):
                    page.fill("#password", password)
                    print("✅ 密码填写完成")
                    take_enhanced_screenshot(context, "GitHub密码填写完成")
                else:
                    print("❌ 未找到密码输入框")
                    take_enhanced_screenshot(context, "未找到GitHub密码输入框")
                    browser.close()
                    return

                commit_btn = page.locator("input[name='commit']").first
                if commit_btn.is_visible(timeout=5000):
                    commit_btn.click()
                    print("✅ 登录表单已提交")
                    take_enhanced_screenshot(context, "GitHub登录表单提交完成")
                    time.sleep(3)
                else:
                    print("❌ 未找到登录提交按钮")
                    take_enhanced_screenshot(context, "未找到GitHub登录提交按钮")
                    browser.close()
                    return
            else:
                print("⚠️ 已在 GitHub 登录状态，跳过账号密码填写")
                take_enhanced_screenshot(context, "GitHub已登录_跳过账号密码填写")
        except PlaywrightTimeoutError:
            print("❌ 跳转到 GitHub 超时！")
            take_enhanced_screenshot(context, "跳转到GitHub超时")
            browser.close()
            return
        except Exception as e:
            print(f"❌ 处理 GitHub 登录表单失败: {str(e)}")
            take_enhanced_screenshot(context, "处理GitHub登录表单失败")
            browser.close()
            return

        # 5. 处理2FA验证
        print("✅ [Step 5] 检查 2FA 验证页面...")
        page.wait_for_timeout(2000)
        take_enhanced_screenshot(context, "检查2FA验证页面初始状态")

        try:
            is_2fa_page = "two-factor" in page.url or page.locator("#app_totp").count() > 0 or page.get_by_text("authentication code").count() > 0
            if is_2fa_page:
                print("✅ 检测到 2FA 双重验证请求！")
                take_enhanced_screenshot(context, "检测到2FA验证页面")

                if not totp_secret:
                    print("❌ 致命错误: 缺少 GH_2FA_SECRET 环境变量！")
                    take_enhanced_screenshot(context, "2FA验证缺少密钥")
                    browser.close()
                    exit(1)

                totp = pyotp.TOTP(totp_secret)
                token = totp.now()
                print(f"✅ 生成的 2FA 验证码: {token}")

                if page.locator("#app_totp").is_visible(timeout=5000):
                    page.fill("#app_totp", token)
                    take_enhanced_screenshot(context, "2FA验证码填写完成")

                    submit_btn = page.locator("button[type='submit']").first
                    if submit_btn.is_visible(timeout=3000):
                        submit_btn.click()
                        print("✅ 2FA 验证码已提交")
                        take_enhanced_screenshot(context, "2FA验证码提交完成")
                        time.sleep(3)
                    else:
                        page.keyboard.press("Enter")
                        print("✅ 按回车提交 2FA 验证码")
                        take_enhanced_screenshot(context, "2FA验证码回车提交完成")
                        time.sleep(3)
                else:
                    print("❌ 未找到 2FA 验证码输入框")
                    take_enhanced_screenshot(context, "未找到2FA验证码输入框")
            else:
                print("⚠️ 未检测到 2FA 验证页面，跳过")
                take_enhanced_screenshot(context, "未检测到2FA验证页面_跳过")
        except Exception as e:
            print(f"❌ 处理 2FA 验证失败: {str(e)}")
            take_enhanced_screenshot(context, "处理2FA验证失败")

        # 6. 处理授权确认页
        print("✅ [Step 6] 检查授权页面...")
        page.wait_for_timeout(2000)
        take_enhanced_screenshot(context, "检查授权页面初始状态")

        if "authorize" in page.url.lower():
            print("✅ 检测到 GitHub 授权请求")
            try:
                authorize_btn = page.locator("button:has-text('Authorize')").first
                authorize_btn.wait_for(state="visible", timeout=5000)
                authorize_btn.click(force=True)
                print("✅ 授权按钮已点击")
                take_enhanced_screenshot(context, "GitHub授权按钮点击完成")
                time.sleep(3)
            except Exception as e:
                print(f"❌ 授权按钮点击失败: {str(e)}")
                take_enhanced_screenshot(context, "GitHub授权按钮点击失败")
        else:
            print("⚠️ 未检测到授权页面，跳过")
            take_enhanced_screenshot(context, "未检测到GitHub授权页面_跳过")

        # 7. 等待最终页面加载
        print("✅ [Step 7] 等待 ClawCloud 控制台完全加载...")
        try:
            page.wait_for_url(lambda url: "run.claw.cloud" in url and "github.com" not in url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)
            time.sleep(10)
            print("✅ ClawCloud 控制台加载完成")
            take_enhanced_screenshot(context, "ClawCloud控制台加载完成")

            # 检查wxk-in-git文本
            print("✅ [Step 7.1] 检查页面是否包含 'wxk-in-git'...")
            wxk_text_locator = page.get_by_text("wxk-in-git", exact=False)
            take_enhanced_screenshot(context, "检查wxk-in-git文本前")

            try:
                wxk_text_locator.wait_for(state="visible", timeout=5000)
                has_wxk_text = wxk_text_locator.count() > 0
            except PlaywrightTimeoutError:
                has_wxk_text = False

            take_enhanced_screenshot(context, "检查wxk-in-git文本后")
            if has_wxk_text:
                print("✅ 页面中检测到 'wxk-in-git' 文本")
            else:
                print("❌ 页面中未检测到 'wxk-in-git' 文本")
        except PlaywrightTimeoutError:
            print("⚠️ 控制台加载超时")
            take_enhanced_screenshot(context, "ClawCloud控制台加载超时")
            time.sleep(3)

        # 最终结果截图
        final_url = page.url
        print(f"📌 最终页面 URL: {final_url}")
        try:
            page.screenshot(path="login_result.png", full_page=True)
            print("📸 已保存最终结果截图: login_result.png")
        except Exception as e:
            print(f"⚠️ 最终截图失败: {str(e)}")

        # 验证登录成功
        success_indicators = [
            page.get_by_text("App Launchpad").count() > 0,
            page.get_by_text("Devbox").count() > 0,
            "private-team" in final_url,
            "console" in final_url,
            "signin" not in final_url and "github.com" not in final_url
        ]
        is_success = any(success_indicators)

        if is_success:
            print("🎉 登录成功！任务完成。")
        else:
            print("❌ 登录失败！")
            exit(1)

        # 关闭浏览器前最后一次统计页面数
        take_enhanced_screenshot(context, "脚本执行完成_关闭浏览器前")

        # 处理浏览器关闭
        if not is_ci_env:
            try:
                input("按 Enter 键关闭浏览器...")
            except EOFError:
                print("\n⚠️ 非交互式环境，自动关闭浏览器")
        else:
            print("✅ CI环境运行，自动关闭浏览器")
        
        browser.close()


if __name__ == "__main__":
    print("="*50)
    print("ClawCloud GitHub 自动登录脚本（多页面监控版）")
    print("="*50)
    run_login()
