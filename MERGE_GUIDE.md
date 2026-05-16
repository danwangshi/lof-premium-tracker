# 合并到原作者仓库操作指南

## 📋 前置准备

### 1. 添加原仓库为 upstream

```bash
# 添加 MistyBridge 原仓库
git remote add upstream https://github.com/MistyBridge/lof-premium-tracker.git

# 验证远程仓库
git remote -v
# 应该看到：
# origin    https://github.com/danwangshi/lof-premium-tracker.git (fetch/push)
# upstream  https://github.com/MistyBridge/lof-premium-tracker.git (fetch/push)
```

### 2. 同步最新代码

```bash
# 获取 upstream 最新代码
git fetch upstream

# 切换到主分支
git checkout main

# 合并 upstream 的 main 分支
git merge upstream/main

# 如果有冲突，解决后提交
git add .
git commit -m "Merge upstream changes"

# 推送到你的仓库
git push origin main
```

---

## 🔀 创建 Pull Request

### 方式一：通过 GitHub Web 界面（推荐）

#### Step 1: 推送你的分支

```bash
# 确保 dev 分支已推送
git push origin dev
```

#### Step 2: 在 GitHub 上创建 PR

1. 访问：https://github.com/MistyBridge/lof-premium-tracker
2. 点击 **"Pull requests"** 标签
3. 点击 **"New pull request"**
4. 设置对比：
   - **base repository**: `MistyBridge/lof-premium-tracker`
   - **base**: `main` (或 `master`)
   - **head repository**: `danwangshi/lof-premium-tracker`
   - **compare**: `dev`
5. 点击 **"Create pull request"**

#### Step 3: 填写 PR 信息

**标题建议：**
```
feat: 协作开发功能合并 - 场内份额追踪、申购限额筛选、365天历史图表
```

**描述内容：**
复制 `PR_DESCRIPTION.md` 的内容粘贴到描述框中。

**关键要点：**
- ✅ 清晰说明新增功能
- ✅ 列出 API 变更
- ✅ 标注数据库变更
- ✅ 提供测试清单
- ✅ 注明贡献者

#### Step 4: 提交 PR

点击 **"Create pull request"** 按钮。

---

### 方式二：使用 GitHub CLI（命令行）

```bash
# 安装 gh CLI: https://cli.github.com/

# 登录 GitHub
gh auth login

# 创建 PR
gh pr create \
  --repo MistyBridge/lof-premium-tracker \
  --base main \
  --head danwangshi:dev \
  --title "feat: 协作开发功能合并 - 场内份额追踪、申购限额筛选、365天历史图表" \
  --body-file PR_DESCRIPTION.md
```

---

## 📝 PR 提交后的工作

### 1. 等待 Review

- 原作者可能会提出修改建议
- 及时回复评论和问题
- 根据反馈调整代码

### 2. 处理冲突（如果有）

```bash
# 如果 upstream 有更新，需要重新同步
git fetch upstream
git checkout dev
git merge upstream/main

# 解决冲突后
git add .
git commit -m "Resolve merge conflicts"
git push origin dev
```

### 3. PR 被接受后

- 感谢原作者的 Review
- 考虑后续持续贡献
- 更新本地 README 中的贡献者信息

---

## ⚠️ 注意事项

### 1. 保持礼貌和专业

- PR 描述清晰简洁
- 尊重原作者的代码风格
- 积极回应反馈

### 2. 文档完整性

- 确保所有新增功能都有文档说明
- 更新 CHANGELOG
- 提供清晰的测试步骤

### 3. 向后兼容

- 确认无破坏性变更
- 原有 API 保持兼容
- 数据库迁移脚本完整

### 4. 代码质量

- 遵循项目代码规范
- 添加必要的注释
- 清理调试代码

---

## 🎯 预期结果

### 成功合并后

1. **你的贡献会被记录**
   - Git 历史中保留你的 commits
   - GitHub Contributors 列表显示你的名字

2. **README 可能需要调整**
   - 原作者可能会将你的贡献添加到原项目的 Contributors 部分
   - 或者保留你当前的"贡献者"章节

3. **后续协作**
   - 可以继续提交新功能
   - 参与 Issue 讨论
   - Help 其他用户

---

## 📞 如果 PR 未被接受

### 可能的原因

1. **功能方向不一致**
   - 原作者可能有不同的产品规划
   - 建议先开 Issue 讨论

2. **代码质量问题**
   - 根据反馈重构代码
   - 补充测试用例

3. **维护负担考虑**
   - 简化功能，降低复杂度
   - 提供更清晰的文档

### 备选方案

1. **保持独立分支**
   - 继续维护 `danwangshi/lof-premium-tracker`
   - 定期同步上游更新
   - 吸引其他用户 Fork 你的版本

2. **创建新项目**
   - 如果分歧较大，可以考虑独立发展
   - 在 README 中注明基于原版

3. **社区 fork**
   - 鼓励社区使用你的版本
   - 建立独立的社区生态

---

## 📚 相关资源

- [GitHub PR 最佳实践](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)
- [开源项目贡献指南](https://opensource.guide/how-to-contribute/)
- [Git 协作工作流](https://www.atlassian.com/git/tutorials/comparing-workflows)

---

## ✅ 检查清单

提交 PR 前确认：

- [ ] 已添加 upstream 远程仓库
- [ ] 已同步最新 upstream 代码
- [ ] 所有测试通过
- [ ] 文档已更新
- [ ] PR 描述清晰完整
- [ ] 无敏感信息泄露（如 API Key）
- [ ] 代码符合项目规范
- [ ] 准备好回应 Review 意见

---

**祝你好运！🎉**
