# 时间掌控者 (TimeMaster)

一个基于 Python + Flask 的个人时间管理系统，集成了 DeepSeek AI 智能排程功能。

## 功能特点

### 1. 用户系统
- 用户注册/登录/退出
- 密码哈希加密存储
- 个人偏好设置

### 2. 任务管理
- 创建任务（标题、描述、预计耗时、截止日期、优先级、分类）
- 支持重复任务（每天/每周/每周指定天）
- 任务列表（支持按状态、优先级、分类筛选和排序）
- 编辑、删除、标记完成

### 3. 智能日程安排（核心功能）
- AI 自动生成今日/本周计划
- 根据任务优先级和截止日期智能排程
- 考虑用户时间偏好（每日开始/结束时间、最大工作时长）
- 自动安排休息时间
- 时间轴形式展示

### 4. 每日反馈
- 对每个时间段提交完成情况
- 记录实际花费时间
- 添加备注心得

### 5. 总结报表
- 自动生成日报、周报、月报
- 完成率统计
- 各类别时间占比（饼图）
- 生产力趋势（柱状图）
- AI 生成总结与建议

### 6. 奖励系统
- 自定义奖励规则（分类 + 目标时长）
- 自动累计各分类时长
- 进度条显示
- 达成提醒和兑现标记

### 7. 主仪表盘
- 今日日程时间轴
- 紧急任务提醒
- 今日完成进度
- 最新总结摘要
- 奖励进度小卡片

## 技术栈

- **后端**: Python 3.10+ / Flask 3.0
- **数据库**: SQLite + SQLAlchemy
- **前端**: Bootstrap 5 + Jinja2 模板
- **图表**: Chart.js
- **AI**: DeepSeek API
- **认证**: Flask-Login

## 安装步骤

### 1. 克隆项目

```bash
cd G:\Yuanxue2026\time_manage
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

编辑 `.env` 文件，填入你的 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=your_actual_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
FLASK_SECRET_KEY=your-random-secret-key-here
```

**获取 DeepSeek API Key：**
1. 访问 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 注册/登录账号
3. 在「API Keys」页面创建新的 API Key
4. 复制 API Key 到 `.env` 文件中

### 4. 运行应用

```bash
python app.py
```

应用将在 `http://localhost:5000` 启动。

### 5. 注册账号

1. 访问 `http://localhost:5000/auth/register`
2. 填写用户名、邮箱、密码
3. 注册后自动跳转到登录页面

## 使用指南

### 首次使用流程

1. **设置时间偏好**
   - 点击右上角用户名 → 设置
   - 设置每日开始/结束时间
   - 设置每日最大工作时长

2. **创建任务**
   - 点击「任务管理」→「新建任务」
   - 填写任务信息
   - 可以创建一次性任务或重复任务

3. **生成智能日程**
   - 点击「日程安排」
   - 选择「生成今日计划」或「生成本周计划」
   - AI 会根据任务自动生成时间表

4. **提交反馈**
   - 完成任务后点击「反馈」
   - 记录实际花费时间和心得

5. **查看总结**
   - 点击「总结报表」
   - 生成日报/周报/月报
   - 查看 AI 分析和建议

6. **设置奖励**
   - 点击「奖励中心」
   - 添加奖励规则（如：运动累计10小时 → 买一杯奶茶）
   - 系统会自动追踪进度

## 项目结构

```
time_manage/
├── app.py                 # 主应用入口
├── models.py              # 数据库模型
├── filters.py             # 自定义过滤器
├── requirements.txt       # 依赖包列表
├── .env                   # 环境变量配置
├── .env.example           # 环境变量示例
├── routes/                # 路由蓝图
│   ├── auth.py           # 用户认证
│   ├── tasks.py          # 任务管理
│   ├── schedule.py       # 日程安排（AI）
│   ├── summary.py        # 总结报表（AI）
│   └── reward.py         # 奖励系统
├── templates/             # Jinja2 模板
│   ├── base.html         # 基础模板
│   ├── login.html        # 登录页面
│   ├── register.html     # 注册页面
│   ├── dashboard.html    # 仪表盘
│   ├── task_list.html    # 任务列表
│   ├── task_form.html    # 任务表单
│   ├── schedule.html     # 日程安排
│   ├── feedback.html     # 反馈表单
│   ├── summary.html      # 总结详情
│   ├── summary_list.html # 总结列表
│   ├── reward.html       # 奖励中心
│   └── settings.html     # 设置页面
└── static/                # 静态文件
    ├── css/              # 自定义样式
    └── js/               # 自定义脚本
```

## 常见问题

### Q: AI 日程生成失败怎么办？
A: 请检查 `.env` 文件中的 `DEEPSEEK_API_KEY` 是否正确配置，并确保账户有足够的余额。

### Q: 如何备份数据？
A: 数据库文件是 `timemaster.db`，直接复制该文件即可备份。

### Q: 可以部署到生产环境吗？
A: 可以，建议使用 Gunicorn 或 uWSGI 作为 WSGI 服务器，并修改 `FLASK_SECRET_KEY` 为随机字符串。

### Q: 如何更改端口？
A: 修改 `app.py` 最后一行的 `port` 参数。

## 许可证

MIT License

## 作者

Created with Claude Code
