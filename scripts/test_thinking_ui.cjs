// Browser regression: actual composer markup/CSS + model selector, synthetic catalog.
// No application data is changed and no provider is contacted.
// NODE_PATH=<playwright packages> node scripts/test_thinking_ui.cjs
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const html = read('app/static/index.html');
const markup = html.match(/<div class="chat-model-bar"[\s\S]*?(?=\s*<div class="input-row")/)[0];
const output = path.join(root, 'data', 'screens');
fs.mkdirSync(output, {recursive: true});

(async () => {
    const browser = await chromium.launch({headless: true, ...(process.platform === 'win32' ? {channel: 'msedge'} : {})});
    try {
        for (const [name, width, panelWidth] of [['desktop', 1100, 420], ['phone', 390, 358], ['floating', 700, 320]]) {
            const page = await browser.newPage({viewport: {width, height: 600}});
            const errors = [];
            page.on('pageerror', e => errors.push(e.message));
            await page.setContent(`<style>${read('app/static/css/main.css')}\n${read('app/static/css/v2/chat.css')}
              body{padding:16px}.test-panel{width:${panelWidth}px;max-width:100%;border:1px solid #ddd;padding:14px;border-radius:16px}</style>
              <div class="test-panel">${markup}</div>`);
            await page.addScriptTag({content: `
              window.AppState = {sessionId:null,session:null,pendingPick:null,catalog:{
                default:{provider:'openai',model:'gpt-6.1-sol'},
                thinking_levels:[{value:'low',label:'低'},{value:'medium',label:'中'},{value:'high',label:'高'},{value:'xhigh',label:'超高'},{value:'max',label:'最高'},{value:'off',label:'关闭'}],
                models:[{provider:'openai',model:'gpt-6.1-sol',thinking:'optional',thinking_levels:['low','medium','high','xhigh','max'],default_thinking:'medium',thinking_source:'docs'},
                        {provider:'openai',model:'gpt-4o',thinking:'none',thinking_levels:[]},
                        {provider:'deepseek',model:'deepseek-flash',thinking:'optional',thinking_levels:['off','low','high','max'],default_thinking:'high',thinking_source:'docs'},
                        {provider:'anthropic',model:'remote-model',thinking:'optional',thinking_levels:['low','high','max'],default_thinking:'high',thinking_source:'remote'}]}};
              window.esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
              window.updateModelInfo = () => {};
              window.toast = msg => window.lastToast = msg;
              window.API = {put:async (url, patch) => ({...AppState.session,...patch})};
            `});
            await page.addScriptTag({content: read('app/static/js/v2/models.js')});
            await page.evaluate(() => renderModelBar());
            const slider = page.locator('#chat-thinking');
            assert.equal(await slider.getAttribute('max'), '4');
            assert.equal(await slider.inputValue(), '1');
            const box = await slider.boundingBox();
            // Actual mouse drag, followed by keyboard control, both save native values.
            await page.mouse.move(box.x + box.width / 4, box.y + box.height / 2);
            await page.mouse.down();
            await page.mouse.move(box.x + box.width - 2, box.y + box.height / 2, {steps: 8});
            await page.mouse.up();
            await page.waitForFunction(() => currentPick().thinking === 'max');
            await slider.focus();
            await page.keyboard.press('Home');
            await page.waitForFunction(() => currentPick().thinking === 'low');
            await page.keyboard.press('End');
            await page.waitForFunction(() => currentPick().thinking === 'max');
            assert.match(await slider.getAttribute('aria-valuetext'), /max/);
            await page.screenshot({path: path.join(output, `thinking-${name}.png`)});
            await page.selectOption('#chat-model', 'openai:gpt-4o');
            assert.equal(await page.locator('#chat-thinking-wrap').isVisible(), false);
            assert.equal(await page.evaluate(() => currentPick().thinking), '');
            await page.selectOption('#chat-model', 'deepseek:deepseek-flash');
            assert.equal(await slider.getAttribute('max'), '3');
            assert.equal(await slider.inputValue(), '2');
            await slider.focus(); await page.keyboard.press('Home');
            await page.waitForFunction(() => currentPick().thinking === 'off');
            await page.selectOption('#chat-model', 'anthropic:remote-model');
            assert.equal(await slider.getAttribute('max'), '2');
            assert.match(await page.locator('#chat-thinking-source').textContent(), /远程/);
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            // An unsuccessful persistence must revert the visible choice.
            await page.evaluate(() => {
                AppState.pendingPick = null;
                AppState.sessionId = 'fake-session';
                AppState.session = {provider:'openai',model:'gpt-6.1-sol',thinking:'medium'};
                API.put = async () => { throw Error('simulated failure'); };
                renderModelBar();
            });
            await slider.focus(); await page.keyboard.press('End');
            await page.waitForFunction(() => !!window.lastToast);
            assert.equal(await slider.inputValue(), '1');
            assert.equal(await page.evaluate(() => currentPick().thinking), 'medium');
            assert.deepEqual(errors, []);
            console.log(`${name}: drag, keyboard, native levels, hidden state, persistence rollback, width OK`);
            await page.close();
        }
    } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
