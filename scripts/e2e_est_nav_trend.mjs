/**
 * 详情页「每日收盘估算净值 vs 实际净值」趋势的端到端验证。
 *
 * 验的是用户报告的那件事：详情页里应该能看到每日收盘估算的效果 ——
 * 估算净值跟真实净值到底差多少、趋势如何。
 *
 * 修复前的实测症状：30 天里 est_nav 只有 1 天非空（而且那 1 天取的是净值公布
 * 之后的切片，误差被放大约 45 倍）。
 *
 *   node scripts/e2e_est_nav_trend.mjs [url]
 */
import { chromium } from 'playwright';

const TARGET = process.argv[2] || 'https://jinkuaicha.com/#/lof';
const CODE = process.env.CODE || '161725';
const EXPECTED_DAYS = Number(process.env.EXPECTED_DAYS || 20);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

await page.addInitScript(() => {
  try { sessionStorage.setItem('jkc_welcome_shown', '1'); } catch (e) {}
});

const fail = (msg) => { console.error('✗ ' + msg); failures.push(msg); };
const failures = [];

// 本地跑时把 /api/** 转发到线上后端
{
  const origin = new URL(TARGET).origin;
  if (/localhost|127\.0\.0\.1/.test(origin)) {
    await page.route('**/api/**', async (route) => {
      const u = new URL(route.request().url());
      const resp = await route.fetch({ url: 'https://jinkuaicha.com' + u.pathname + u.search });
      await route.fulfill({ response: resp });
    });
  }
}

await page.goto(TARGET, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForFunction(
  () => document.querySelectorAll('#fundTableBody tr.fund-row').length > 0,
  null, { timeout: 60000 });

// 用真实用户路径：搜索代码 → 点开详情
await page.fill('#searchInput', CODE);
await page.waitForFunction(
  (code) => {
    const rows = Array.from(document.querySelectorAll('#fundTableBody tr.fund-row'));
    return rows.length > 0 && rows.every(r => r.dataset.code === code);
  },
  CODE, { timeout: 20000 }).catch(async () => {
    // 搜索没生效就退回到直接点行
    await page.fill('#searchInput', '');
  });

const rowSel = `#fundTableBody tr.fund-row[data-code="${CODE}"]`;
await page.waitForSelector(rowSel, { timeout: 20000 });
await page.click(rowSel + ' td:nth-child(1)').catch(() => page.click(rowSel));

await page.waitForSelector('#fdPhase2', { state: 'visible', timeout: 30000 });
await page.waitForFunction(
  () => window.SPA?._app?._detailChart != null, null, { timeout: 30000 });

// 切到「估算净值 + 场外净值」模式（走真实下拉，走 change 事件）
await page.selectOption('#fdIndSelect', 'est_nav,nav');
await page.waitForFunction(
  () => window.SPA?._app?._detailMode === 'est_nav,nav', null, { timeout: 15000 });
// 默认是「七日」，切到「一月」才看得到趋势；顺带验证区间切换后摘要会重算
await page.selectOption('#fdRangeSelect', '30');
await page.waitForFunction(
  () => (window.SPA?._app?._detailDays || 0) === 30, null, { timeout: 15000 });
await page.waitForFunction(
  () => {
    const el = document.getElementById('fdEstAccuracy');
    return el && el.style.display !== 'none' && el.textContent.trim().length > 0;
  }, null, { timeout: 30000 });
await page.waitForFunction(
  () => (window.SPA?._app?._detailChart?.data?.labels?.length || 0) > 20,
  null, { timeout: 30000 });

const result = await page.evaluate(() => {
  const app = window.SPA._app;
  const chart = app._detailChart;
  const ds = chart.data.datasets;
  const est = ds.find(d => d._key === 'est_nav');
  const nav = ds.find(d => d._key === 'nav');
  const price = ds.find(d => d._key === 'price');
  const estVals = est ? est.data : [];
  const navVals = nav ? nav.data : [];
  return {
    labels: chart.data.labels.length,
    estNonEmpty: estVals.filter(v => v != null).length,
    navNonEmpty: navVals.filter(v => v != null).length,
    estHidden: est ? !!est.hidden : null,
    navHidden: nav ? !!nav.hidden : null,
    priceHidden: price ? !!price.hidden : null,
    summary: document.getElementById('fdEstAccuracy').textContent.trim(),
    mode: app._detailMode,
    chartDataLen: app._detailChartChartDataLen,
  };
});

// 直接问后端要原始数据，核对前端展示的与接口一致
const api = await page.evaluate(async (code) => {
  const r = await fetch(`https://api.jinkuaicha.com/api/v1/funds/${code}/chart?days=30`);
  return r.ok ? await r.json() : { error: r.status };
}, CODE);

const rows = Array.isArray(api) ? api : (api.chart || api.data || []);
const apiEst = rows.filter(r => r.est_nav != null);
const apiErr = rows.filter(r => r.est_nav_error != null);

console.log('=== 图表数据集 ===');
console.log(`  坐标点数 ${result.labels}`);
console.log(`  估算净值序列非空 ${result.estNonEmpty} / ${result.labels}  (hidden=${result.estHidden})`);
console.log(`  场外净值序列非空 ${result.navNonEmpty} / ${result.labels}  (hidden=${result.navHidden})`);
console.log('=== 准确度摘要 ===');
console.log('  ' + result.summary);
console.log('=== 接口原始数据 ===');
console.log(`  近 30 日 est_nav 非空 ${apiEst.length} 天，可核对误差 ${apiErr.length} 天`);
for (const r of apiErr.slice(-5)) {
  console.log(`    ${r.date}  估算 ${r.est_nav}  实际 ${r.est_nav_realized}  误差 ${r.est_nav_error >= 0 ? '+' : ''}${r.est_nav_error}%`);
}

// ── 断言 ──
// 核心断言是"覆盖率"而不是点数：修复前 30 天里只有 1 天有值，
// 所以任何"展示区间的每一个点都该有估算值"的检查都能抓住这个 bug。
if (result.labels < EXPECTED_DAYS) {
  fail(`图上一共只有 ${result.labels} 个坐标点（期望 ≥${EXPECTED_DAYS}）—— 区间没切到 30 日？`);
}
if (result.estNonEmpty !== result.labels) {
  fail(`估算净值只有 ${result.estNonEmpty}/${result.labels} 个点有值 —— 趋势是断的`);
}
if (result.estHidden) fail('估算净值序列被隐藏了，用户看不到趋势');
if (result.navNonEmpty !== result.labels) {
  fail(`场外净值只有 ${result.navNonEmpty}/${result.labels} 个点有值`);
}
if (!/估算准确度/.test(result.summary)) fail('准确度摘要没出现：' + result.summary);
if (!/平均误差/.test(result.summary)) fail('摘要里没有平均误差：' + result.summary);
if (apiErr.length === 0) fail('接口没有返回任何可核对的误差');
if (apiEst.length < EXPECTED_DAYS) fail(`接口 est_nav 只有 ${apiEst.length} 天（期望 ≥${EXPECTED_DAYS}）`);

// 误差必须小得合理：这是"估算器有效"的证据。若取错切片（取到净值公布之后的），
// 误差会跳到 2%+ —— 正是用户看到的那个假象。
const worst = Math.max(...apiErr.map(r => Math.abs(Number(r.est_nav_error))));
console.log(`  最大误差 ${worst.toFixed(4)}%`);
if (worst > 1.5) fail(`最大误差 ${worst}% 过大，可能又取到净值公布之后的切片了`);

await page.screenshot({ path: 'est_nav_trend.png', fullPage: false });
console.log('\n截图: est_nav_trend.png');

if (errors.length) {
  console.log('\n控制台错误:');
  for (const e of errors) console.log('  ' + e);
  fail(`有 ${errors.length} 条控制台错误`);
}

await browser.close();

if (failures.length) {
  console.error(`\n✗ ${failures.length} 项未通过`);
  process.exit(1);
}
console.log('\n✓ 详情页估算净值趋势已验证');
