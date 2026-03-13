# 文件名: login_script.py
# 作用: 自动登录 ClawCloud Run，支持 GitHub 账号密码 + 2FA 自动验证
# 新增：每一步关键操作后截图，便于排查错误
import os
import sys
import time
import pyotp  # 用于生成 2FA 验证码
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# 封装截图函数，简化重复代码
def take_screenshot(page, step_name, screenshot_dir="screenshots"):
    """
    生成步骤截图
    :param page: playwright的page对象
    :param step_name: 步骤名称（用于文件名）
    :param screenshot_dir: 截图保存目录
    """
    # 创建截图目录（不存在则创建）
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
    # 生成截图文件名（避免特殊字符）
    filename = f"{screenshot_dir}/step_{step_name.replace(' ', '_')}_{int(time.time())}.png"
    try:
        # 截取完整页面，保存截图
        page.screenshot(path=filename, full_page=True)
        print(f"📸 已保存[{step_name}]截图: {filename}")
    except Exception as e:
        print(f"⚠️ [{step_name}]截图失败: {str(e)}")


def run_login():
    # 1. 获取环境变量中的敏感信息（建议优先用环境变量，避免硬编码）
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")

    if not username or not password:
        print("❌ 错误: 必须设置 GH_USERNAME 和 GH_PASSWORD 环境变量。")
        return

    print("✅ [Step 1] 启动浏览器...")
    with sync_playwright() as p:
        # 关键配置：根据运行环境自动调整headless（CI环境用无头模式）
        is_ci_env = os.environ.get("CI") == "true" or not sys.stdout.isatty()
        browser = p.chromium.launch(
            headless=is_ci_env,  # CI环境无头运行，本地环境显示浏览器
            slow_mo=500,         # 每个操作延迟500ms，平衡速度和稳定性
            args=[
                "--start-maximized",  # 浏览器最大化
                "--no-sandbox",       # 解决权限问题
                "--disable-blink-features=AutomationControlled"  # 避免被检测为自动化工具
            ]
        )
        # 设置浏览器上下文为最大化
        context = browser.new_context(viewport=None)
        # 禁用自动化提示（防止GitHub检测）
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """)
        page = context.new_page()
        # Step1截图：浏览器启动后
        take_screenshot(page, "浏览器启动完成")

        # 2. 访问 ClawCloud 登录页（增加异常处理）
        target_url = "https://ap-southeast-1.run.claw.cloud/"
        print(f"✅ [Step 2] 正在访问: {target_url}")
        try:
            page.goto(target_url, timeout=30000)
            # 等待页面完全加载（优先等待DOM，再等网络空闲）
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=20000)
            print("✅ 页面加载完成")
            time.sleep(20)  # 等待元素渲染
            # Step2截图：ClawCloud登录页加载完成
            take_screenshot(page, "ClawCloud登录页加载完成")
        except PlaywrightTimeoutError:
            print("❌ 页面加载超时！请检查网络或目标网址是否正确")
            take_screenshot(page, "ClawCloud登录页加载超时")
            browser.close()
            return

        # 3. 点击 GitHub 登录按钮（核心修复：多策略定位+强制点击）
        print("✅ [Step 3] 寻找 GitHub 登录按钮...")
        github_button = None
        # 定义多种定位策略，提高命中率
        locator_strategies = [
            "button:has-text('GitHub')",
            "a:has-text('GitHub')",
            "[data-provider='github']",
            "[href*='github']",
            "//button[contains(text(), 'GitHub')]",
            "//a[contains(text(), 'GitHub')]"
        ]

        # 遍历定位策略，找到可用的按钮
        for locator_str in locator_strategies:
            try:
                temp_locator = page.locator(locator_str)
                # 检查元素是否存在且可见
                if temp_locator.count() > 0 and temp_locator.is_visible(timeout=2000):
                    github_button = temp_locator
                    print(f"✅ 找到 GitHub 按钮 (定位策略: {locator_str})")
                    break
            except:
                continue

        # Step3截图1：查找GitHub按钮后（无论是否找到）
        take_screenshot(page, "查找GitHub按钮后")

        if not github_button:
            print("❌ 未找到 GitHub 登录按钮！")
            browser.close()
            return

        # 核心修复：多种点击方式确保生效
        try:
            # 1. 先滚动到按钮位置（避免按钮在视口外）
            github_button.scroll_into_view_if_needed()
            time.sleep(1)
            
            # 2. 优先使用playwright的click（带force=True强制点击）
            github_button.click(force=True, timeout=5000)
            print("✅ GitHub 按钮点击成功（常规点击）")
            # Step3截图2：GitHub按钮点击成功
            take_screenshot(page, "GitHub按钮点击成功")
        except:
            try:
                # 备用方案：使用JavaScript点击（绕过前端事件拦截）
                page.evaluate("(element) => element.click()", github_button.element_handle())
                print("✅ GitHub 按钮点击成功（JS点击）")
                # Step3截图2：GitHub按钮点击成功（JS方式）
                take_screenshot(page, "GitHub按钮点击成功_JS方式")
            except Exception as e:
                print(f"❌ GitHub 按钮点击失败: {str(e)}")
                take_screenshot(page, "GitHub按钮点击失败")
                browser.close()
                return

        # 4. 处理 GitHub 登录表单（增加等待和异常处理）
        print("✅ [Step 4] 等待跳转到 GitHub 登录页...")
        try:
            # 等待跳转到GitHub域名（放宽URL匹配条件）
            page.wait_for_url(lambda url: "github.com" in url, timeout=30000)
            print(f"✅ 已跳转到: {page.url}")
            time.sleep(20)
            # Step4截图1：跳转到GitHub页面
            take_screenshot(page, "跳转到GitHub页面")
            
            # 填写账号密码（增加存在性检查）
            if "login" in page.url.lower():
                print("✅ 开始填写 GitHub 账号密码...")
                # 检查账号输入框是否存在
                if page.locator("#login_field").is_visible(timeout=5000):
                    page.fill("#login_field", username)
                    print("✅ 账号填写完成")
                    # Step4截图2：账号填写完成
                    take_screenshot(page, "GitHub账号填写完成")
                else:
                    print("❌ 未找到账号输入框 (#login_field)")
                    take_screenshot(page, "未找到GitHub账号输入框")
                    browser.close()
                    return
                
                # 检查密码输入框是否存在
                if page.locator("#password").is_visible(timeout=5000):
                    page.fill("#password", password)
                    print("✅ 密码填写完成")
                    # Step4截图3：密码填写完成
                    take_screenshot(page, "GitHub密码填写完成")
                else:
                    print("❌ 未找到密码输入框 (#password)")
                    take_screenshot(page, "未找到GitHub密码输入框")
                    browser.close()
                    return
                
                # 点击登录按钮（增加定位容错）
                commit_btn = page.locator("input[name='commit']").first
                if commit_btn.is_visible(timeout=5000):
                    commit_btn.click()
                    print("✅ 登录表单已提交")
                    # Step4截图4：登录表单提交完成
                    take_screenshot(page, "GitHub登录表单提交完成")
                    time.sleep(3)
                else:
                    print("❌ 未找到登录提交按钮")
                    take_screenshot(page, "未找到GitHub登录提交按钮")
                    browser.close()
                    return
            else:
                print("⚠️ 已在 GitHub 登录状态，跳过账号密码填写")
                take_screenshot(page, "GitHub已登录_跳过账号密码填写")
        except PlaywrightTimeoutError:
            print("❌ 跳转到 GitHub 超时！可能已自动登录或按钮点击未生效")
            take_screenshot(page, "跳转到GitHub超时")
            browser.close()
            return
        except Exception as e:
            print(f"❌ 处理 GitHub 登录表单失败: {str(e)}")
            take_screenshot(page, "处理GitHub登录表单失败")
            browser.close()
            return

        # 5. 处理 2FA 双重验证（优化逻辑）
        print("✅ [Step 5] 检查 2FA 验证页面...")
        page.wait_for_timeout(2000)
        # Step5截图1：检查2FA页面初始状态
        take_screenshot(page, "检查2FA验证页面初始状态")
        
        try:
            # 多条件检测2FA页面
            is_2fa_page = "two-factor" in page.url or page.locator("#app_totp").count() > 0 or page.get_by_text("authentication code").count() > 0
            
            if is_2fa_page:
                print("✅ 检测到 2FA 双重验证请求！")
                # Step5截图2：检测到2FA验证页面
                take_screenshot(page, "检测到2FA验证页面")
                
                if not totp_secret:
                    print("❌ 致命错误: 检测到 2FA 但未配置 GH_2FA_SECRET 环境变量！")
                    take_screenshot(page, "2FA验证缺少密钥")
                    browser.close()
                    exit(1)
                
                # 生成TOTP验证码
                totp = pyotp.TOTP(totp_secret)
                token = totp.now()
                print(f"✅ 生成的 2FA 验证码: {token}")
                
                # 填写验证码（增加容错）
                totp_input = page.locator("#app_totp").first
                if totp_input.is_visible(timeout=5000):
                    totp_input.fill(token)
                    # Step5截图3：2FA验证码填写完成
                    take_screenshot(page, "2FA验证码填写完成")
                    
                    # 点击提交按钮（多定位策略）
                    submit_btn = page.locator("button[type='submit']").first
                    if submit_btn.is_visible(timeout=3000):
                        submit_btn.click()
                        print("✅ 2FA 验证码已提交")
                        # Step5截图4：2FA验证码提交完成
                        take_screenshot(page, "2FA验证码提交完成")
                        time.sleep(3)
                    else:
                        # 备用：按回车提交
                        page.keyboard.press("Enter")
                        print("✅ 按回车提交 2FA 验证码")
                        # Step5截图4：2FA验证码回车提交完成
                        take_screenshot(page, "2FA验证码回车提交完成")
                        time.sleep(3)
                else:
                    print("❌ 未找到 2FA 验证码输入框 (#app_totp)")
                    take_screenshot(page, "未找到2FA验证码输入框")
            else:
                print("⚠️ 未检测到 2FA 验证页面，跳过")
                take_screenshot(page, "未检测到2FA验证页面_跳过")
        except Exception as e:
            print(f"❌ 处理 2FA 验证失败: {str(e)}")
            take_screenshot(page, "处理2FA验证失败")
            page.screenshot(path="2fa_process_fail.png")

        # 6. 处理授权确认页
        print("✅ [Step 6] 检查授权页面...")
        page.wait_for_timeout(2000)
        # Step6截图1：检查授权页面初始状态
        take_screenshot(page, "检查授权页面初始状态")
        
        if "authorize" in page.url.lower():
            print("✅ 检测到 GitHub 授权请求")
            try:
                authorize_btn = page.locator("button:has-text('Authorize')").first
                authorize_btn.wait_for(state="visible", timeout=5000)
                authorize_btn.click(force=True)
                print("✅ 授权按钮已点击")
                # Step6截图2：授权按钮点击完成
                take_screenshot(page, "GitHub授权按钮点击完成")
                time.sleep(3)
            except Exception as e:
                print(f"❌ 授权按钮点击失败: {str(e)}")
                take_screenshot(page, "GitHub授权按钮点击失败")
        else:
            print("⚠️ 未检测到授权页面，跳过")
            take_screenshot(page, "未检测到GitHub授权页面_跳过")

        # 7. 等待最终页面加载完成（核心优化：延长等待+等待加载状态）
        print("✅ [Step 7] 等待 ClawCloud 控制台完全加载...")
        try:
            # 等待页面跳回ClawCloud且网络空闲
            page.wait_for_url(lambda url: "run.claw.cloud" in url and "github.com" not in url, timeout=30000)
            # 等待页面完全加载（networkidle确保没有加载中的请求）
            page.wait_for_load_state("networkidle", timeout=20000)
            # 额外等待10秒，确保动态内容渲染完成（避免加载圆圈）
            time.sleep(10)
            print("✅ ClawCloud 控制台加载完成")
            # Step7截图1：ClawCloud控制台加载完成
            take_screenshot(page, "ClawCloud控制台加载完成")
            
            # ========== 新增：判断页面是否包含"wxk-in-git" ==========
            print("✅ [Step 7.1] 检查页面是否包含 'wxk-in-git'...")
            # 方式1：精准定位包含该文本的元素（推荐）
            wxk_text_locator = page.get_by_text("wxk-in-git", exact=False)
            # Step7截图2：检查wxk-in-git文本前
            take_screenshot(page, "检查wxk-in-git文本前")
            
            # 等待元素出现（最多等待5秒）
            try:
                wxk_text_locator.wait_for(state="visible", timeout=5000)
                has_wxk_text = wxk_text_locator.count() > 0
            except PlaywrightTimeoutError:
                # 超时说明未找到该文本
                has_wxk_text = False
            
            # Step7截图3：检查wxk-in-git文本后
            take_screenshot(page, "检查wxk-in-git文本后")
            
            if has_wxk_text:
                print("✅ 页面中检测到 'wxk-in-git' 文本")
            else:
                print("❌ 页面中未检测到 'wxk-in-git' 文本")
        except PlaywrightTimeoutError:
            print("⚠️ 控制台加载超时，但登录流程已完成，继续截图")
            take_screenshot(page, "ClawCloud控制台加载超时")
            time.sleep(3)  # 兜底等待

        final_url = page.url
        print(f"📌 最终页面 URL: {final_url}")

        # 8. 最终结果截图
        try:
            page.screenshot(path="login_result.png", full_page=True)  # full_page=True截取整页
            print("📸 已保存最终结果截图: login_result.png")
        except Exception as e:
            print(f"⚠️ 最终截图失败: {str(e)}")

        # 9. 验证是否成功
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
            print("❌ 登录失败！请查看 screenshots 目录下的截图排查原因。")
            exit(1)

        # 核心修复：移除input()，根据环境决定是否保持浏览器打开
        if not is_ci_env:
            # 仅本地交互式环境显示等待输入
            try:
                input("按 Enter 键关闭浏览器...")
            except EOFError:
                print("\n⚠️ 非交互式环境，自动关闭浏览器")
        else:
            print("✅ CI环境运行，自动关闭浏览器")
        
        browser.close()


if __name__ == "__main__":
    # 增加启动提示
    print("="*50)
    print("ClawCloud GitHub 自动登录脚本启动（全步骤截图版）")
    print("="*50)
    run_login()
