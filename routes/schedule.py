from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, time
import requests
import json
import re
from models import db, Task, Schedule, Feedback, RewardProgress, FixedSchedule, ImportantDate

schedule_bp = Blueprint('schedule', __name__)


def call_deepseek_api(prompt, max_tokens=2000, timeout=60):
    """调用DeepSeek API"""
    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    base_url = current_app.config.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')

    if not api_key:
        error_msg = 'DeepSeek API key not configured'
        print(error_msg)
        with open('api_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: {error_msg}\n')
        return None

    try:
        # 禁用代理，避免系统代理干扰
        session = requests.Session()
        session.trust_env = False  # 忽略系统代理设置

        with open('api_debug.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: Calling API with URL: {base_url}/v1/chat/completions\n')
            f.write(f'{datetime.now()}: API Key: {api_key[:10]}...\n')
            f.write(f'{datetime.now()}: Max tokens: {max_tokens}, Timeout: {timeout}\n')

        response = session.post(
            f'{base_url}/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': '你是一个高效的时间管理助手，专门帮助用户制定合理的时间安排。'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': 0.7
            },
            timeout=timeout,
            verify=True  # SSL验证
        )

        with open('api_debug.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: Response status: {response.status_code}\n')

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            error_msg = f'DeepSeek API error: {response.status_code} - {response.text}'
            print(error_msg)
            with open('api_error.log', 'a', encoding='utf-8') as f:
                f.write(f'{datetime.now()}: {error_msg}\n')
            return None

    except requests.exceptions.ProxyError as e:
        error_msg = f'DeepSeek API proxy error: {str(e)}'
        print(error_msg)
        print('提示：请检查系统代理设置或尝试关闭代理')
        with open('api_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: {error_msg}\n')
        return None
    except requests.exceptions.SSLError as e:
        error_msg = f'DeepSeek API SSL error: {str(e)}'
        print(error_msg)
        print('提示：SSL连接失败，可能需要配置VPN或检查网络')
        with open('api_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: {error_msg}\n')
        return None
    except requests.exceptions.Timeout as e:
        error_msg = f'DeepSeek API timeout after {timeout}s: {str(e)}'
        print(error_msg)
        print(f'提示：连接超时（{timeout}秒），生成本周计划需要更长时间，请稍后重试')
        with open('api_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: {error_msg}\n')
        return None
    except Exception as e:
        error_msg = f'DeepSeek API exception: {type(e).__name__}: {str(e)}'
        print(error_msg)
        with open('api_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: {error_msg}\n')
        return None


def parse_schedule_from_ai(ai_response, date):
    """解析AI返回的时间表"""
    schedules = []

    # 支持多种格式解析
    lines = ai_response.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('-') or line.startswith('='):
            continue

        # 尝试匹配时间格式: HH:MM - HH:MM 或 HH:MM~HH:MM
        time_pattern = r'(\d{1,2}):(\d{2})\s*[-~到至]\s*(\d{1,2}):(\d{2})'
        match = re.search(time_pattern, line)

        if match:
            start_hour, start_min, end_hour, end_min = match.groups()

            # 提取任务标题（去掉时间部分和后面的分类、优先级等信息）
            task_title = line
            # 先去掉时间
            for m in re.finditer(time_pattern, line):
                task_title = task_title.replace(m.group(0), '').strip()
            # 去掉开头的分隔符
            task_title = task_title.lstrip('| 　，、').strip()
            # 去掉 | 及后面的内容（分类、优先级等）
            if '|' in task_title:
                task_title = task_title.split('|')[0].strip()
            # 去掉多余的单位描述
            task_title = re.sub(r'\s*\|\s*.*?小时.*$', '', task_title)
            task_title = re.sub(r'\s*\|\s*\d+分钟.*$', '', task_title)
            task_title = task_title.strip()

            if task_title:
                schedules.append({
                    'start_time': time(int(start_hour), int(start_min)),
                    'end_time': time(int(end_hour), int(end_min)),
                    'task_title': task_title,
                    'line': line  # 保存原始行用于解析其他信息
                })

    return schedules


@schedule_bp.route('/')
@login_required
def view_schedule():
    """查看日程"""
    # 获取日期参数，默认今天
    date_str = request.args.get('date', '')
    if date_str:
        try:
            view_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            view_date = datetime.now().date()
    else:
        view_date = datetime.now().date()

    # 获取当天的日程
    schedules = Schedule.query.filter(
        Schedule.user_id == current_user.id,
        Schedule.date == view_date
    ).order_by(Schedule.start_time).all()

    # 计算前后的日期
    prev_date = view_date - timedelta(days=1)
    next_date = view_date + timedelta(days=1)

    return render_template('schedule.html',
                         schedules=schedules,
                         view_date=view_date,
                         prev_date=prev_date,
                         next_date=next_date)


@schedule_bp.route('/generate', methods=['POST'])
@login_required
def generate_schedule():
    """生成智能日程"""
    schedule_type = request.form.get('type', 'today')  # today 或 week
    start_date = datetime.now().date()

    if schedule_type == 'week':
        # 生成本周日程
        end_date = start_date + timedelta(days=6)
    else:
        end_date = start_date

    # 获取未完成的任务，分离会议和普通任务
    all_tasks = Task.query.filter(
        Task.user_id == current_user.id,
        Task.status == 'pending'
    ).all()

    # 检查是否有之前安排但未完成的任务（延续任务）
    previous_uncompleted = []
    if schedule_type == 'today':
        # 获取今天之前的未完成日程
        prev_schedules = Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.date < start_date,
            Schedule.generated_by_ai == True,
            Schedule.status == 'scheduled'
        ).all()
        previous_uncompleted = [s for s in prev_schedules if s.task_id]
    else:
        # 获取本周开始之前的未完成日程
        prev_schedules = Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.date < start_date,
            Schedule.generated_by_ai == True,
            Schedule.status == 'scheduled'
        ).all()
        previous_uncompleted = [s for s in prev_schedules if s.task_id]

    meeting_tasks = [t for t in all_tasks if t.is_meeting]
    regular_tasks = [t for t in all_tasks if not t.is_meeting]

    # 获取固定日程
    fixed_schedules = []
    if schedule_type == 'today':
        weekday = start_date.weekday()
        day_fixed = FixedSchedule.query.filter(
            FixedSchedule.user_id == current_user.id,
            FixedSchedule.is_active == True,
            FixedSchedule.day_of_week == weekday,
            FixedSchedule.start_date <= start_date,
            db.or_(FixedSchedule.end_date == None, FixedSchedule.end_date >= start_date)
        ).all()
        fixed_schedules.extend(day_fixed)
    else:
        # 获取本周所有固定日程
        for i in range(7):
            day = start_date + timedelta(days=i)
            weekday = day.weekday()
            day_fixed = FixedSchedule.query.filter(
                FixedSchedule.user_id == current_user.id,
                FixedSchedule.is_active == True,
                FixedSchedule.day_of_week == weekday,
                FixedSchedule.start_date <= day,
                db.or_(FixedSchedule.end_date == None, FixedSchedule.end_date >= day)
            ).all()
            fixed_schedules.extend([(fs, day) for fs in day_fixed])

    # 获取重要日子
    important_dates = ImportantDate.query.filter(
        ImportantDate.user_id == current_user.id,
        ImportantDate.event_date >= start_date,
        ImportantDate.event_date <= end_date
    ).all()

    if not all_tasks and not fixed_schedules:
        flash('没有待安排的任务和固定日程', 'warning')
        return redirect(url_for('schedule.view_schedule'))

    # 构建任务列表（会议在前）
    tasks_data = []
    for task in meeting_tasks:
        task_dict = task.to_dict()
        if task.deadline:
            days_until = (task.deadline.date() - start_date).days
            if days_until >= -7:
                tasks_data.append(task_dict)
        else:
            tasks_data.append(task_dict)

    for task in regular_tasks:
        task_dict = task.to_dict()
        if task.deadline:
            days_until = (task.deadline.date() - start_date).days
            if days_until >= -7:
                tasks_data.append(task_dict)
        else:
            tasks_data.append(task_dict)

    # 构建固定日程信息
    fixed_info = []
    if schedule_type == 'today':
        for fs in fixed_schedules:
            fixed_info.append({
                'title': fs.title,
                'day': '周一二三四五六日'[start_date.weekday()],
                'start': fs.start_time.strftime('%H:%M'),
                'end': fs.end_time.strftime('%H:%M'),
                'category': fs.category,
                'location': fs.location
            })
    else:
        for fs, day in fixed_schedules:
            fixed_info.append({
                'title': fs.title,
                'day': f"{day.month}月{day.day}日 周{'一二三四五六日'[day.weekday()]}",
                'start': fs.start_time.strftime('%H:%M'),
                'end': fs.end_time.strftime('%H:%M'),
                'category': fs.category,
                'location': fs.location
            })

    # 构建重要日子信息
    important_info = []
    for imp in important_dates:
        important_info.append({
            'title': imp.title,
            'date': imp.event_date.strftime('%m月%d日'),
            'type': imp.date_type,
            'time': imp.event_time.strftime('%H:%M') if imp.event_time else None
        })

    # 构建AI提示词
    if schedule_type == 'today':
        date_range = f"今天（{start_date.strftime('%Y年%m月%d日')}）"
    else:
        end_date_str = end_date.strftime('%Y年%m月%d日')
        date_range = f"本周（{start_date.strftime('%Y年%m月%d日')} 至 {end_date_str}）"

    # 构建提示词
    prompt_parts = [
        f"""你是一个高效的时间管理助手。请为用户生成{date_range}的详细时间表。

用户设置：
- 每日可用时间：{current_user.daily_start_hour}:00 - {current_user.daily_end_hour}:00
- 每日最大工作时长：{current_user.max_work_hours}小时"""
    ]

    # 添加固定日程信息
    if fixed_info:
        prompt_parts.append("\n【固定日程 - 必须优先安排，不可移动】")
        for fi in fixed_info:
            loc = f" @ {fi['location']}" if fi.get('location') else ""
            prompt_parts.append(f"  {fi['day']} {fi['start']}-{fi['end']}: {fi['title']}{loc}")

    # 添加重要日子
    if important_info:
        prompt_parts.append("\n【重要日子 - 请在日程中标注】")
        for imp in important_info:
            time_str = f" {imp['time']}" if imp['time'] else ""
            prompt_parts.append(f"  {imp['date']}{time_str}: {imp['title']} ({imp['type']})")

    # 添加延续任务提醒（之前安排但未完成的任务）
    if previous_uncompleted:
        prompt_parts.append("\n【延续任务 - 这些任务之前已安排但未完成，请优先安排】")
        for sched in previous_uncompleted:
            date_str = sched.date.strftime('%m月%d日')
            prompt_parts.append(f"  - {sched.task_title}（原计划{date_str}未完成，请重新安排）")

    # 添加会议任务
    if meeting_tasks:
        prompt_parts.append("\n【会议任务 - 最高优先级，必须在指定时间段安排】")
        for task in meeting_tasks:
            deadline_str = task.deadline.strftime('%m-%d %H:%M') if task.deadline else '无截止时间'
            loc = f" @ {task.location}" if task.location else ""
            # 检查是否是延续任务
            is_continuation = any(s.task_id == task.id for s in previous_uncompleted)
            cont_note = " [延续]" if is_continuation else ""
            prompt_parts.append(f"  - {task.title}{loc} | 截止: {deadline_str} | 优先级: {task.priority} | 预计: {task.estimated_hours}小时{cont_note}")

    # 添加普通任务
    if regular_tasks:
        prompt_parts.append("\n【普通任务】")
        for task in regular_tasks:
            deadline_str = task.deadline.strftime('%m-%d %H:%M') if task.deadline else '无截止时间'
            # 检查是否是延续任务
            is_continuation = any(s.task_id == task.id for s in previous_uncompleted)
            cont_note = " [延续]" if is_continuation else ""
            prompt_parts.append(f"  - {task.title} | 截止: {deadline_str} | 优先级: {task.priority} | 预计: {task.estimated_hours}小时{cont_note}")

    prompt_parts.append(f"""
请按以下要求生成时间表：
1. 【固定日程优先】首先将所有固定日程填入对应时间段，这些时间不可占用
2. 【会议优先】会议任务必须优先安排，且在输出时标注 [会议]
3. 【工作时段限制】工作/学习任务只安排在 {current_user.daily_start_hour}:00 - {current_user.daily_end_hour}:00 之间
4. 【每日锻炼】每天下午15:00-16:00固定安排锻炼身体（跑步、健身、运动等）
5. 按截止日期和优先级安排其他任务
6. 每项任务之间留10-15分钟缓冲时间（会议前后可不留缓冲）
7. 每天工作时间不超过{current_user.max_work_hours}小时，包含适当休息
8. 将相似类别的任务尽量安排在一起
9. 【重要】每周计划必须为每天单独输出，每天开始时必须标注日期，格式：=== 2月24日 周一 ===
10. 输出格式要求：
   时间段 | 任务标题 | 预计时长 | 分类 | 优先级

示例格式：
=== 2月23日 周日 ===
10:00-10:15 | 晨间计划 | 15分钟 | 生活 | 低
10:15-12:00 | 完成数学作业 | 1.75小时 | 上课 | 高
12:00-12:15 | 休息 | 15分钟 | 生活 | 低
12:15-13:30 | 午餐和午休 | 1.25小时 | 生活 | 低
13:30-14:45 | [会议] 组会讨论 | 1.25小时 | 会议 | 高
14:45-15:00 | 休息 | 15分钟 | 生活 | 低
15:00-16:00 | 锻炼身体 | 1小时 | 健康 | 高
16:00-17:00 | 阅读学习 | 1小时 | 上课 | 中

=== 2月24日 周一 ===
10:00-10:15 | 晨间计划 | 15分钟 | 生活 | 低
...

请从{current_user.daily_start_hour}:00开始安排，到17:00结束（晚上不安排工作学习任务）。

请只输出时间表，不要其他解释文字。""")

    prompt = '\n'.join(prompt_parts)

    # 调用DeepSeek API
    # 根据类型设置不同的max_tokens和timeout
    if schedule_type == 'week':
        max_tokens = 8000  # 本周计划需要更多token
        timeout = 120      # 增加超时时间到2分钟
    else:
        max_tokens = 4000  # 今日计划
        timeout = 60       # 1分钟

    # 检查API配置
    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        flash('DeepSeek API密钥未配置，请在.env文件中设置DEEPSEEK_API_KEY', 'danger')
        return redirect(url_for('schedule.view_schedule'))

    ai_response = call_deepseek_api(prompt, max_tokens=max_tokens, timeout=timeout)

    if not ai_response:
        flash('AI日程生成失败：API调用无响应，请检查网络连接和API密钥', 'danger')
        return redirect(url_for('schedule.view_schedule'))

    # 删除旧的AI生成的日程（但保留已完成的日程）
    if schedule_type == 'today':
        Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.date == start_date,
            Schedule.generated_by_ai == True,
            Schedule.status != 'completed'  # 保留已完成的日程
        ).delete()
    else:
        Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.date.between(start_date, end_date),
            Schedule.generated_by_ai == True,
            Schedule.status != 'completed'  # 保留已完成的日程
        ).delete()

    # 先插入固定日程
    if schedule_type == 'today':
        for fs in fixed_schedules:
            schedule = Schedule(
                user_id=current_user.id,
                date=start_date,
                start_time=fs.start_time,
                end_time=fs.end_time,
                task_title=fs.title,
                category=fs.category,
                location=fs.location,
                is_meeting=True,  # 固定日程视为重要事项
                generated_by_ai=True,
                ai_reasoning=f"固定日程: {fs.description or ''}"
            )
            db.session.add(schedule)
    else:
        for fs, day in fixed_schedules:
            schedule = Schedule(
                user_id=current_user.id,
                date=day,
                start_time=fs.start_time,
                end_time=fs.end_time,
                task_title=fs.title,
                category=fs.category,
                location=fs.location,
                is_meeting=True,
                generated_by_ai=True,
                ai_reasoning=f"固定日程: {fs.description or ''}"
            )
            db.session.add(schedule)

    # 解析AI响应，按日期分组
    schedule_by_date = {}
    current_date = start_date

    # 按行处理AI响应
    lines = ai_response.strip().split('\n')
    date_pattern = r'===\s*(\d{1,2})月(\d{1,2})日\s*周[一二三四五六日天]?\s*==='

    for line in lines:
        line = line.strip()

        # 检查是否是日期标记行
        date_match = re.search(date_pattern, line)
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            try:
                current_date = datetime(start_date.year, month, day).date()
            except:
                current_date = start_date
            continue  # 跳过日期标记行本身

        # 解析时间格式的行
        time_pattern = r'(\d{1,2}):(\d{2})\s*[-~到至]\s*(\d{1,2}):(\d{2})'
        time_match = re.search(time_pattern, line)

        if time_match:
            start_hour, start_min = int(time_match.group(1)), int(time_match.group(2))
            end_hour, end_min = int(time_match.group(3)), int(time_match.group(4))

            # 提取任务标题
            task_title = line
            for m in re.finditer(time_pattern, line):
                task_title = task_title.replace(m.group(0), '').strip()
            task_title = task_title.lstrip('| 　，、').strip()
            if '|' in task_title:
                task_title = task_title.split('|')[0].strip()
            task_title = re.sub(r'\s*\|\s*.*?小时.*$', '', task_title)
            task_title = re.sub(r'\s*\|\s*\d+分钟.*$', '', task_title)
            task_title = task_title.strip()

            if task_title and current_date:
                if current_date not in schedule_by_date:
                    schedule_by_date[current_date] = []
                schedule_by_date[current_date].append({
                    'start_time': time(start_hour, start_min),
                    'end_time': time(end_hour, end_min),
                    'task_title': task_title,
                    'line': line
                })

    # 保存AI生成的日程到数据库
    for sched_date, sched_list in schedule_by_date.items():
        for sched in sched_list:
            # 检查该时间段是否已有日程（防止时间冲突）
            existing = Schedule.query.filter_by(
                user_id=current_user.id,
                date=sched_date,
                start_time=sched['start_time'],
                end_time=sched['end_time']
            ).first()

            if existing:
                continue  # 跳过已有日程的时间段

            # 检查是否是会议
            task_title_lower = sched['task_title'].lower()
            is_meeting = '[会议]' in sched['task_title'] or 'meeting' in task_title_lower or '组会' in sched['task_title'] or '会议' in sched['task_title']

            schedule = Schedule(
                user_id=current_user.id,
                date=sched_date,
                start_time=sched['start_time'],
                end_time=sched['end_time'],
                task_title=sched['task_title'].replace('[会议]', '').replace('[会议]', '').strip(),
                is_break='休息' in sched['task_title'] or 'break' in task_title_lower,
                is_meeting=is_meeting,
                generated_by_ai=True
            )

            # 尝试匹配任务
            matching_task = None
            for task in all_tasks:
                if task.title in sched['task_title'] or sched['task_title'] in task.title:
                    matching_task = task
                    break

            if matching_task:
                schedule.task_id = matching_task.id
                schedule.category = matching_task.category
                schedule.location = matching_task.location
                schedule.is_meeting = matching_task.is_meeting or is_meeting
            else:
                # 尝试从原始行提取分类
                if '分类' in sched['line'] or '|' in sched['line']:
                    parts = sched['line'].split('|')
                    if len(parts) >= 4:
                        category = parts[3].strip()
                        schedule.category = category

            db.session.add(schedule)

    try:
        db.session.commit()

        # 取消旧的未完成日程（已延续到新日程的）
        cancelled_count = 0
        for old_sched in previous_uncompleted:
            # 检查是否在新日程中安排了相同的任务
            new_has_task = Schedule.query.filter(
                Schedule.user_id == current_user.id,
                Schedule.date.between(start_date, end_date if schedule_type == 'week' else start_date),
                Schedule.task_id == old_sched.task_id,
                Schedule.generated_by_ai == True
            ).first()
            if new_has_task:
                # 标记旧日程为已取消
                old_sched.status = 'cancelled'
                cancelled_count += 1

        db.session.commit()

        # 统计保留的已完成日程数量
        kept_count = Schedule.query.filter(
            Schedule.user_id == current_user.id,
            Schedule.date.between(start_date, end_date if schedule_type == 'week' else start_date),
            Schedule.generated_by_ai == True,
            Schedule.status == 'completed'
        ).count()

        msg = f'已生成{schedule_type == "week" and "本周" or "今日"}智能日程，会议和固定日程已优先安排'
        if kept_count > 0:
            msg += f'（已保留 {kept_count} 个已完成的日程）'
        if cancelled_count > 0:
            msg += f'（已取消 {cancelled_count} 个旧的未完成日程）'

        flash(msg, 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'保存日程失败：{str(e)}', 'danger')

    return redirect(url_for('schedule.view_schedule'))


@schedule_bp.route('/<int:schedule_id>/feedback', methods=['GET', 'POST'])
@login_required
def feedback(schedule_id):
    """提交日程反馈"""
    schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        # 查找或创建反馈记录
        feedback_record = Feedback.query.filter_by(schedule_id=schedule_id).first()

        if not feedback_record:
            feedback_record = Feedback(
                user_id=current_user.id,
                schedule_id=schedule_id
            )
            db.session.add(feedback_record)

        # 更新反馈信息
        feedback_record.completion_status = request.form.get('completion_status', '未开始')
        actual_hours_str = request.form.get('actual_hours', '')
        if actual_hours_str:
            try:
                feedback_record.actual_hours = float(actual_hours_str)
            except:
                feedback_record.actual_hours = None
        feedback_record.notes = request.form.get('notes', '').strip()

        # 更新日程状态
        schedule.status = feedback_record.completion_status

        # 更新奖励进度
        if feedback_record.completion_status in ['已完成', '部分完成'] and feedback_record.actual_hours:
            if schedule.category:
                update_reward_progress(schedule.category, feedback_record.actual_hours)

        # 如果有关联任务且已完成，更新任务状态
        if schedule.task_id and feedback_record.completion_status == '已完成':
            task = Task.query.get(schedule.task_id)
            if task and task.status == 'pending':
                # 检查是否所有关联的日程都完成了
                all_schedules = Schedule.query.filter_by(task_id=task.id).all()
                if all(s.status == 'completed' for s in all_schedules):
                    task.status = 'completed'
                    task.completed_at = datetime.now()

        try:
            db.session.commit()
            flash('反馈已提交', 'success')
            return redirect(url_for('schedule.view_schedule'))
        except Exception as e:
            db.session.rollback()
            flash(f'提交失败：{str(e)}', 'danger')

    feedback_record = Feedback.query.filter_by(schedule_id=schedule_id).first()

    return render_template('feedback.html',
                         schedule=schedule,
                         feedback=feedback_record)


def update_reward_progress(category, hours):
    """更新奖励进度 - 完成日程增加打卡次数和时长"""
    progress = RewardProgress.query.filter_by(
        user_id=current_user.id,
        category=category
    ).first()

    if not progress:
        progress = RewardProgress(
            user_id=current_user.id,
            category=category,
            total_points=0,
            total_hours=0.0,
            checkin_count=0
        )
        db.session.add(progress)

    # 完成日程增加打卡次数和时长
    progress.checkin_count += 1
    progress.total_hours = (progress.total_hours or 0) + hours
    progress.last_updated = datetime.now()
    db.session.commit()  # 添加提交


def decrease_reward_progress(category, hours):
    """减少奖励进度 - 取消完成时减少打卡次数和时长"""
    progress = RewardProgress.query.filter_by(
        user_id=current_user.id,
        category=category
    ).first()

    if progress:
        # 减少打卡次数和时长，确保不为负数
        progress.checkin_count = max(0, progress.checkin_count - 1)
        progress.total_hours = max(0, (progress.total_hours or 0) - hours)
        progress.last_updated = datetime.now()
        db.session.commit()


@schedule_bp.route('/<int:schedule_id>/toggle_status', methods=['POST'])
@login_required
def toggle_status(schedule_id):
    """快捷切换日程完成状态"""
    try:
        schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

        # 获取请求的状态
        new_status = request.json.get('status')

        if not new_status:
            return jsonify({'success': False, 'error': '缺少状态参数'}), 400

        if new_status not in ['scheduled', 'completed', 'partial', 'cancelled']:
            return jsonify({'success': False, 'error': f'无效的状态: {new_status}'}), 400

        # 保存旧状态，用于判断是否需要更新进度
        old_status = schedule.status

        # 更新状态
        schedule.status = new_status

        # 计算时长
        duration = (datetime.combine(schedule.date, schedule.end_time) -
                   datetime.combine(schedule.date, schedule.start_time)).total_seconds() / 3600

        # 如果从非完成状态改为完成状态，增加进度
        if new_status == 'completed' and old_status != 'completed':
            if schedule.category:
                update_reward_progress(schedule.category, duration)

        # 如果从完成状态改为非完成状态，减少进度
        elif old_status == 'completed' and new_status != 'completed':
            if schedule.category:
                decrease_reward_progress(schedule.category, duration)

        # 提交状态更新
        db.session.commit()

        # 如果有关联任务，更新任务状态
        if schedule.task_id:
            task = Task.query.get(schedule.task_id)
            if task:
                all_schedules = Schedule.query.filter_by(task_id=task.id).all()
                if all(s.status == 'completed' for s in all_schedules):
                    task.status = 'completed'
                    task.completed_at = datetime.now()
                elif task.status == 'completed' and new_status != 'completed':
                    task.status = 'pending'
                    task.completed_at = None
                db.session.commit()

        status_map = {
            'scheduled': '已安排',
            'completed': '已完成',
            'partial': '部分完成',
            'cancelled': '已取消'
        }

        return jsonify({
            'success': True,
            'status': new_status,
            'status_text': status_map.get(new_status, new_status)
        })
    except Exception as e:
        db.session.rollback()
        with open('toggle_error.log', 'a', encoding='utf-8') as f:
            f.write(f'{datetime.now()}: Error toggling schedule {schedule_id}: {str(e)}\n')
        return jsonify({'success': False, 'error': str(e)}), 500


@schedule_bp.route('/manual', methods=['GET', 'POST'])
@login_required
def manual_add():
    """手动添加日程"""
    # 获取待办任务列表
    pending_tasks = Task.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).order_by(Task.priority.desc(), Task.deadline.asc()).all() or []
    # Debug: 打印查询结果
    print(f'[DEBUG MANUAL_ADD] Pending tasks count: {len(pending_tasks)}')
    for task in pending_tasks:
        print(f'[DEBUG MANUAL_ADD] Task: id={task.id}, title={task.title}, status={task.status}, priority={task.priority}')

    if request.method == 'POST':
        date_str = request.form.get('date', '')
        start_time_str = request.form.get('start_time', '')
        end_time_str = request.form.get('end_time', '')
        category = request.form.get('category', '其他').strip() or '其他'

        # 支持选择任务或手动输入
        task_id = request.form.get('task_id', '')
        title_input = request.form.get('title', '').strip()

        title = title_input
        task_id_value = None

        if task_id and task_id != 'custom':
            task = Task.query.filter_by(id=int(task_id), user_id=current_user.id).first()
            if task:
                title = task.title
                task_id_value = task.id
                # 如果任务有分类，使用任务的分类
                if not category or category == '其他':
                    category = task.category or '其他'

        try:
            schedule_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time()

            schedule = Schedule(
                user_id=current_user.id,
                date=schedule_date,
                start_time=start_time,
                end_time=end_time,
                task_title=title,
                category=category,
                task_id=task_id_value,
                generated_by_ai=False
            )

            db.session.add(schedule)
            db.session.commit()
            flash('日程已添加', 'success')
            return redirect(url_for('schedule.view_schedule', date=date_str))

        except Exception as e:
            db.session.rollback()
            flash(f'添加失败：{str(e)}', 'danger')

    return render_template('schedule_manual.html', pending_tasks=pending_tasks)


@schedule_bp.route('/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_schedule(schedule_id):
    """编辑日程"""
    schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()

    # 获取待办任务列表，用于下拉选择
    pending_tasks = Task.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).order_by(Task.priority.desc(), Task.deadline.asc()).all() or []
    # Debug: 打印查询结果
    print(f'[DEBUG EDIT_SCHEDULE] Pending tasks count: {len(pending_tasks)}')
    for task in pending_tasks:
        print(f'[DEBUG EDIT_SCHEDULE] Task: id={task.id}, title={task.title}, status={task.status}, priority={task.priority}')

    if request.method == 'POST':
        # 保存原始值用于比较
        old_status = schedule.status
        old_category = schedule.category
        old_start = schedule.start_time
        old_end = schedule.end_time
        old_date = schedule.date

        # 计算原始时长
        old_duration = (datetime.combine(old_date, old_end) -
                       datetime.combine(old_date, old_start)).total_seconds() / 3600

        # 获取表单数据 - 支持选择任务或手动输入
        task_id = request.form.get('task_id', '')
        title_input = request.form.get('title', '').strip()

        if task_id and task_id != 'custom':
            # 从任务列表选择
            task = Task.query.filter_by(id=int(task_id), user_id=current_user.id).first()
            if task:
                schedule.task_id = task.id
                schedule.task_title = task.title
                # 如果任务有分类，使用任务的分类
                if not schedule.category or schedule.category == '其他':
                    schedule.category = task.category or '其他'
            else:
                schedule.task_title = title_input or schedule.task_title
        else:
            # 手动输入
            schedule.task_id = None
            schedule.task_title = title_input

        schedule.category = request.form.get('category', '其他').strip() or '其他'
        schedule.location = request.form.get('location', '').strip()

        # 时间设置
        date_str = request.form.get('date', '')
        start_time_str = request.form.get('start_time', '')
        end_time_str = request.form.get('end_time', '')

        try:
            schedule.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            schedule.start_time = datetime.strptime(start_time_str, '%H:%M').time()
            schedule.end_time = datetime.strptime(end_time_str, '%H:%M').time()
        except Exception as e:
            flash('请输入正确的日期和时间格式', 'danger')
            return redirect(url_for('schedule.edit_schedule', schedule_id=schedule_id))

        # 计算新时长
        new_duration = (datetime.combine(schedule.date, schedule.end_time) -
                       datetime.combine(schedule.date, schedule.start_time)).total_seconds() / 3600

        # 状态设置
        schedule.status = request.form.get('status', 'scheduled')
        new_status = schedule.status

        try:
            # 处理进度变化
            # 1. 如果状态从完成改为非完成，减少进度
            if old_status == 'completed' and new_status != 'completed':
                if old_category:
                    decrease_reward_progress(old_category, old_duration)

            # 2. 如果状态从非完成改为完成，增加进度
            elif new_status == 'completed' and old_status != 'completed':
                if schedule.category:
                    update_reward_progress(schedule.category, new_duration)

            # 3. 如果保持完成状态但时长或分类改变了
            elif old_status == 'completed' and new_status == 'completed':
                # 如果分类改变了
                if old_category != schedule.category:
                    # 减少旧分类的进度
                    if old_category:
                        decrease_reward_progress(old_category, old_duration)
                    # 增加新分类的进度
                    if schedule.category:
                        update_reward_progress(schedule.category, new_duration)
                # 如果分类没变但时长改变了
                elif old_category == schedule.category and schedule.category:
                    # 调整时长差异
                    duration_diff = new_duration - old_duration
                    if duration_diff != 0:
                        if duration_diff > 0:
                            update_reward_progress(schedule.category, duration_diff)
                        else:
                            decrease_reward_progress(schedule.category, -duration_diff)

            db.session.commit()
            flash('日程更新成功', 'success')
            return redirect(url_for('schedule.view_schedule', date=schedule.date.strftime('%Y-%m-%d')))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'danger')

    return render_template('schedule_edit.html', schedule=schedule, pending_tasks=pending_tasks)


@schedule_bp.route('/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    """删除日程"""
    schedule = Schedule.query.filter_by(id=schedule_id, user_id=current_user.id).first_or_404()
    schedule_date = schedule.date

    # 如果是已完成的日程，需要减少进度
    if schedule.status == 'completed':
        duration = (datetime.combine(schedule.date, schedule.end_time) -
                   datetime.combine(schedule.date, schedule.start_time)).total_seconds() / 3600
        if schedule.category:
            decrease_reward_progress(schedule.category, duration)

    try:
        db.session.delete(schedule)
        db.session.commit()
        flash('日程已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败：{str(e)}', 'danger')

    return redirect(url_for('schedule.view_schedule', date=schedule_date.strftime('%Y-%m-%d')))
