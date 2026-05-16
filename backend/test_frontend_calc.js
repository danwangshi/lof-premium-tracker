// 模拟前端计算逻辑（最终版 - 单位：万份，表头显示单位）
const testCases = [
    { shares_incr: 7765.77 },   // 160644: 7765.77万份
    { shares_incr: 5.77 },      // 5.77万份
    { shares_incr: -721.36 },   // -721.36万份
    { shares_incr: 0.0 },       // 0万份
    { shares_incr: 99.99 },     // 99.99万份
    { shares_incr: 100.00 },    // 100万份
    { shares_incr: 9999.99 },   // 9999.99万份
    { shares_incr: 10000.00 },  // 10000万份
    { shares_incr: 123456.78 }, // 123456.78万份
];

testCases.forEach((fund, idx) => {
    let sharesIncrText = '-';
    let sharesIncrClass = 'premium-zero';
    
    if (fund.shares_incr !== null && fund.shares_incr !== undefined) {
        const incr = fund.shares_incr;  // 单位：万份
        // 直接显示数值，保留两位小数
        sharesIncrText = incr.toFixed(2);
        sharesIncrClass = incr > 0 ? 'premium-positive' : incr < 0 ? 'premium-negative' : 'premium-zero';
    }
    
    console.log(`测试 ${idx + 1}: shares_incr=${fund.shares_incr}万 -> 显示: "${sharesIncrText}" (${sharesIncrClass})`);
});
