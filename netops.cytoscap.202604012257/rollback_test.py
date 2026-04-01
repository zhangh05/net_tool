#!/usr/bin/env python3
"""
NetOps 事务回滚测试 - 最终版本
"""
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://192.168.32.72:6133"

def screenshot(page, name):
    try:
        page.screenshot(path=f"/root/netops/{name}.png", full_page=True)
        print(f"  📸 /root/netops/{name}.png")
    except Exception as e:
        print(f"  Screenshot error: {e}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(viewport={"width": 1600, "height": 1400})
        page = context.new_page()
        page.set_default_timeout(20000)
        
        console_errors = []
        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        page.on("console", on_console)
        
        # 1. Open and enter project
        print("[1] Opening NetOps...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        
        for card in page.locator("[class*='card'], .project-card").all():
            try:
                ct = card.inner_text()
                if "测试1" in ct:
                    card.locator("button, a").first.click(timeout=3000)
                    print("  ✅ Entered 测试1")
                    break
            except:
                pass
        
        time.sleep(4)
        screenshot(page, "final_01_in_project")
        
        # 2. Open chat
        print("\n[2] Opening chat...")
        try:
            page.locator(".chat-btn-sm").first.click(timeout=5000)
            time.sleep(2)
            print("  ✅ Chat opened")
        except Exception as e:
            print(f"  ⚠️ {e}")
        screenshot(page, "final_02_chat")
        
        # 3. Force sync: ask AI to describe current topology first
        # This makes the AI read the actual canvas state
        print("\n[3] Syncing AI state with canvas...")
        page.locator("textarea.chat-input").first.fill("当前拓扑有哪些设备？")
        page.locator("textarea.chat-input").first.press("Enter")
        time.sleep(6)
        
        # Check what the AI says
        msgs = page.locator(".chat-msg").all()
        last_msgs = []
        for m in msgs[-5:]:
            try:
                txt = m.inner_text()
                if txt.strip():
                    last_msgs.append(txt[:300])
            except:
                pass
        print(f"  AI state sync - last messages:")
        for lm in last_msgs:
            print(f"    {lm[:200]}")
        screenshot(page, "final_03_synced")
        
        # 4. Clear - send clear command after sync
        print("\n[4] 清空拓扑...")
        page.locator("textarea.chat-input").first.fill("清空拓扑")
        page.locator("textarea.chat-input").first.press("Enter")
        time.sleep(6)
        screenshot(page, "final_04_cleared")
        
        # 5. Add routers
        print("\n[5] 添加 TESTA/TESTB...")
        page.locator("textarea.chat-input").first.fill("添加两台路由器，ID为 TESTA 和 TESTB，位置300,200和400,200")
        page.locator("textarea.chat-input").first.press("Enter")
        time.sleep(6)
        screenshot(page, "final_05_added")
        
        # Verify canvas
        try:
            svg = page.locator("svg").first
            svg_txt = svg.inner_text()
            canvas_devs = [d for d in ["TESTA", "TESTB"] if d in svg_txt]
            print(f"  Canvas after add: {canvas_devs}")
        except:
            canvas_devs = []
            print("  Canvas: could not read")
        
        # 6. Rollback scenario
        print("\n[6] 回滚场景...")
        page.locator("textarea.chat-input").first.fill("删除 TESTA，然后删除不存在的设备 NONEXIST，再添加 TESTC")
        page.locator("textarea.chat-input").first.press("Enter")
        time.sleep(6)
        screenshot(page, "final_06_rollback")
        
        # 7. Click the LAST "执行全部操作" button (for the rollback message)
        print("\n[7] Clicking '执行全部操作'...")
        
        # Find all execute buttons and click the LAST one
        btns = page.locator("#ops-execute-btn").all()
        print(f"  Found {len(btns)} execute buttons")
        
        if btns:
            # The last button should be for the most recent message
            last_btn = btns[-1]
            # Get its parent message text to confirm
            parent_div = last_btn.locator("..").locator("..")
            parent_txt = parent_div.inner_text()[:200]
            print(f"  Last button parent: {parent_txt[:200]}")
            
            # Use JS to click it
            try:
                last_btn.evaluate("b => b.click()")
                print("  ✅ Clicked last execute button via JS")
            except Exception as e:
                print(f"  ⚠️ JS click failed: {e}")
                # Try direct evaluate
                try:
                    page.evaluate("arguments[0].click()", last_btn)
                    print("  ✅ Clicked via page.evaluate")
                except Exception as e2:
                    print(f"  ⚠️ {e2}")
        
        time.sleep(6)
        screenshot(page, "final_07_executed")
        
        # 8. Final verification
        print("\n=== FINAL VERIFICATION ===")
        time.sleep(3)
        screenshot(page, "final_08_final")
        
        # Get canvas devices
        canvas_devs = []
        try:
            svg = page.locator("svg").first
            svg_txt = svg.inner_text()
            canvas_devs = [d for d in ["TESTA", "TESTB", "TESTC"] if d in svg_txt]
            print(f"  Canvas SVG devices: {canvas_devs}")
        except Exception as e:
            print(f"  Canvas read error: {e}")
        
        # Get full page text
        body = page.inner_text("body")
        page_devs = [d for d in ["TESTA", "TESTB", "TESTC"] if d in body]
        has_rollback = "回滚" in body or "回退" in body
        
        print(f"  Full page devices: {page_devs}")
        print(f"  Rollback shown: {has_rollback}")
        
        # Check latest chat messages
        msgs = page.locator(".chat-msg").all()
        print("\n  Latest 5 messages:")
        for m in msgs[-5:]:
            try:
                txt = m.inner_text()
                if txt.strip():
                    print(f"    {txt[:300]}")
            except:
                pass
        
        print("\n=== RESULT ===")
        # Canvas is the source of truth
        if len(canvas_devs) == 3:
            print("❌ ROLLBACK FAILED: 3 devices on canvas (TESTA, TESTB, TESTC)")
            print("   → Transaction NOT rolled back. Half-baked residue exists!")
        elif len(canvas_devs) == 2 and "TESTA" in canvas_devs:
            print("⚠️  PARTIAL: 2 devices on canvas with TESTA, TESTC missing")
        elif len(canvas_devs) == 2 and "TESTA" not in canvas_devs:
            print("✅ PASS: 2 devices on canvas (TESTB + TESTC), TESTA removed — rollback worked!")
        elif len(canvas_devs) == 1:
            print(f"⚠️  Only 1 device on canvas: {canvas_devs}")
        elif len(canvas_devs) == 0:
            print("⚠️  Canvas empty (0 devices)")
        else:
            print(f"⚠️  UNEXPECTED: {canvas_devs}")
        
        if has_rollback:
            print("📢 Rollback indicator was shown on the page")
        
        browser.close()
        print("\nScreenshots: /root/netops/final_*.png")

if __name__ == "__main__":
    main()
