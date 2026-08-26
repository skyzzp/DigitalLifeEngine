"""
DigitalLifeEngine - 数字生命引擎
V0.5：可解释状态推断 + 长期用户画像 + 桌宠成长

这是一个 AI 桌宠数字生命引擎。

V0.1 稳定版功能：
- 输入合法性检查：非数字、负数都会提示重新输入，程序不会崩溃
- 同一天重复运行时，会询问是否覆盖今天的记录，避免产生重复数据
- 程序结束前会暂停，按 Enter 键才退出，方便查看分析结果

V0.2 新增功能：
- 历史表现分析：平均值统计、连续记录天数、三个指数的趋势分析

V0.3 新增功能：
- 桌宠成长系统：根据每天的行为数据获得 XP（经验值）、提升等级、增加亲密度
- 等级提升时会显示升级提示
- 数据文件新增 pet 区域，旧数据文件没有 pet 字段也能正常使用

V0.4 新增功能：
- 记录心情、精力、压力三个 1～5 分的主观指标
- 结合当日指标和近期历史，推断充实、平稳、疲惫、压力偏高四种状态
- 输出判断依据、个性化建议和供上层桌宠使用的反应代码
- 拒绝 nan / inf 等非有限数字，历史分析不再依赖记录原有顺序

V0.5 新增功能：
- 根据全部历史记录生成可重算的长期用户画像
- 区分长期平均特征和最近 7 条记录，避免只看单日状态
- 输出画像成熟度、特征标签、主导状态和个性化陪伴策略
- 每次新增或覆盖记录都会重算画像，不会因覆盖产生累计误差
"""


import json        # 用于读写 JSON 数据文件
import math        # 用于判断输入是否为有限数字
import os          # 用于检查文件和创建目录
from datetime import datetime  # 用于获取今天的日期、做日期计算


# ============================================================
# 配置部分：数据文件的路径和参数
# ============================================================

# 数据目录的名称
DATA_DIR = "data"

# 数据文件的完整路径（data/behavior_data.json）
DATA_FILE = os.path.join(DATA_DIR, "behavior_data.json")

# 趋势判断阈值：
# 最近 3 天的平均值和此前平均值相差超过 5 分，
# 才认为趋势有明显变化（↑ 或 ↓），否则算"变化不明显"（→）
TREND_THRESHOLD = 5


# ============================================================
# 桌宠成长规则（V0.3 新增）
# ============================================================
# 所有成长数值规则集中在这里管理。
# 以后想调整"平衡性"（比如让升级更快），只需要修改这一处，
# 不需要去翻下面的计算代码。

# XP（经验值）规则：桌宠每天根据用户的行为获得经验值
XP_RULES = {
    "per_task": 10,              # 每完成 1 个任务获得 10 XP
    "per_study_hour": 5,         # 学习时间每满 1 小时获得 5 XP
    "per_interaction": 2,        # 每与桌宠互动 1 次获得 2 XP
    "study_index_bonus": 10,     # 学习指数达标时的额外奖励
    "study_index_threshold": 70, # 学习指数达到多少算"达标"
    "streak_bonus": 10,          # 连续记录达标时的额外奖励
    "streak_bonus_days": 3,      # 连续记录达到多少天算"达标"
}

# 亲密度规则：亲密度反映用户和桌宠的关系，范围 0 ~ 100
INTIMACY_RULES = {
    "per_task": 1,               # 每完成 1 个任务增加 1 点
    "per_interaction": 1,        # 每与桌宠互动 1 次增加 1 点
    "daily_record": 1,           # 每天成功记录数据增加 1 点
    "study_index_bonus": 2,      # 学习指数达标时额外增加 2 点
    "study_index_threshold": 70, # 学习指数达到多少算"达标"
    "max": 100,                  # 亲密度上限（下限是 0）
}

# 等级表：累计 XP 达到某个数字后，升到对应等级
# 列表每一项是（最低 XP 要求，等级），从低到高排列
LEVEL_TABLE = [
    (0, 1),      # XP 0 ~ 99     → Lv.1
    (100, 2),    # XP 100 ~ 199  → Lv.2
    (200, 3),    # XP 200 ~ 349  → Lv.3
    (350, 4),    # XP 350 ~ 499  → Lv.4
    (500, 5),    # XP 500 ~ 699  → Lv.5
    (700, 6),    # XP 700 以上    → Lv.6+
]


# ============================================================
# 第一部分：用户输入
# ============================================================

def ask_positive_number(prompt, allow_decimal=True,
                        min_value=0, max_value=None):
    """
    向用户询问一个数字，并做合法性检查。

    检查规则：
    1. 输入必须是数字（否则提示重新输入）
    2. 数字必须是有限值，不能是 nan 或 inf
    3. 数字必须处于指定范围

    参数：
    - prompt - 提示文字，例如 "今天学习了几小时？ "
    - allow_decimal - True 表示允许小数（如 2.5），
                      False 表示只接受整数

    - min_value / max_value - 可接受范围；max_value 为 None 表示无上限

    返回：一个合法数字
    """

    # while True 会一直循环，
    # 直到用户输入了合法的数字，才通过 return 结束循环
    while True:

        # 获取用户输入的一行文字
        user_text = input(prompt)

        # 尝试把文字转换成数字
        # 如果用户输入的不是数字（比如 "abc"），
        # 转换会失败并抛出 ValueError
        try:
            if allow_decimal:
                number = float(user_text)
            else:
                number = int(user_text)
        except ValueError:
            # 转换失败：说明输入的不是有效数字
            # 打印提示，然后继续循环，让用户重新输入
            if allow_decimal:
                print("  输入无效，请输入一个数字。")
            else:
                print("  输入无效，请输入一个整数。")
            continue

        # float("nan") 和 float("inf") 虽然能转换成功，
        # 但不是真正可用于分析的有限数字，必须拒绝
        if not math.isfinite(number):
            print("  请输入有限数字，不能输入 nan 或 inf。")
            continue

        # 检查数字是否处于指定范围
        if number < min_value:
            print(f"  数字不能小于 {min_value}，请重新输入。")
            continue

        if max_value is not None and number > max_value:
            print(f"  数字不能大于 {max_value}，请重新输入。")
            continue

        # 能走到这里，说明输入合法，返回这个数字
        return number


def ask_yes_no(prompt):
    """
    向用户询问一个"是 / 否"问题。

    输入 y 或 yes 表示"是"，输入 n 或 no 表示"否"。
    输入其他内容会提示重新输入。

    参数：prompt - 提示文字
    返回：True 表示"是"，False 表示"否"
    """

    # 一直循环，直到用户给出有效回答
    while True:

        # 获取用户回答，去掉首尾空格并转成小写，方便比较
        answer = input(prompt + "（y/n）").strip().lower()

        # 属于"是"的回答
        if answer in ["y", "yes", "是"]:
            return True

        # 属于"否"的回答
        if answer in ["n", "no", "否"]:
            return False

        # 输入了其他内容，提示后重新询问
        print("  请输入 y 或 n。")


def get_user_input():
    """
    从命令行获取用户今天的行为数据。

    会依次询问七个问题：
    1. 今天学习了几小时
    2. 今天玩游戏多少分钟
    3. 今天完成了几个任务
    4. 今天与桌宠互动了几次
    5. 今日心情、精力、压力各为几分（1～5）

    每个问题都会做合法性检查：
    - 输入非数字会提示重新输入
    - 输入负数会提示重新输入

    返回值：一个字典，包含四项行为数据和三项主观状态数据
    """

    print("=" * 40)
    print("       数字生命引擎 - 每日行为记录")
    print("=" * 40)
    print()

    # 询问今天学习了几小时（允许小数，例如 2.5 小时）
    study_hours = ask_positive_number("今天学习了几小时？ ", allow_decimal=True)

    # 询问今天玩游戏多少分钟（允许小数）
    game_minutes = ask_positive_number("今天玩游戏多少分钟？ ", allow_decimal=True)

    # 询问今天完成了几个任务（必须是整数）
    tasks_completed = ask_positive_number("今天完成了几个任务？ ", allow_decimal=False)

    # 询问今天与桌宠互动了几次（必须是整数）
    interactions = ask_positive_number("今天与桌宠互动了几次？ ", allow_decimal=False)

    print("\n请根据真实感受，为下面三项打 1～5 分：")
    mood = ask_positive_number(
        "今日心情（1=很差，5=很好）： ",
        allow_decimal=False, min_value=1, max_value=5
    )
    energy = ask_positive_number(
        "今日精力（1=很疲惫，5=很充沛）： ",
        allow_decimal=False, min_value=1, max_value=5
    )
    stress = ask_positive_number(
        "今日压力（1=很轻松，5=压力很大）： ",
        allow_decimal=False, min_value=1, max_value=5
    )

    print()

    # 把收集到的数据整理成字典，方便后续使用
    user_data = {
        "study_hours": study_hours,
        "game_minutes": game_minutes,
        "tasks_completed": tasks_completed,
        "interactions": interactions,
        "mood": mood,
        "energy": energy,
        "stress": stress
    }

    return user_data


# ============================================================
# 第二部分：指标计算
# ============================================================

def calculate_study_index(study_hours):
    """
    计算学习指数。

    规则：每学习 1 小时得 10 分，最高 100 分。
    例如：学习 3 小时 → 30 分，学习 12 小时 → 100 分（封顶）

    参数：study_hours - 学习小时数
    返回：学习指数（0 ~ 100）
    """

    # 每小时 10 分
    index = study_hours * 10

    # 不超过 100 分
    if index > 100:
        index = 100

    return index


def calculate_activity_index(game_minutes, tasks_completed):
    """
    计算活跃指数。

    规则：
    - 游戏每 10 分钟得 2 分
    - 每完成 1 个任务得 10 分
    - 最高 100 分

    参数：
    - game_minutes - 游戏分钟数
    - tasks_completed - 完成任务数

    返回：活跃指数（0 ~ 100）
    """

    # 游戏部分得分：每 10 分钟得 2 分
    game_score = (game_minutes / 10) * 2

    # 任务部分得分：每个任务 10 分
    task_score = tasks_completed * 10

    # 两部分相加
    index = game_score + task_score

    # 不超过 100 分
    if index > 100:
        index = 100

    return index


def calculate_interaction_index(interactions):
    """
    计算互动指数。

    规则：每互动 1 次得 10 分，最高 100 分。
    例如：互动 5 次 → 50 分，互动 15 次 → 100 分（封顶）

    参数：interactions - 互动次数
    返回：互动指数（0 ~ 100）
    """

    # 每次互动 10 分
    index = interactions * 10

    # 不超过 100 分
    if index > 100:
        index = 100

    return index


def determine_status(study_index, activity_index, interaction_index):
    """
    根据三个指数判断今日状态。

    规则：
    - 三个指数的平均分 >= 70 → "积极"
    - 三个指数的平均分 >= 40 → "一般"
    - 三个指数的平均分 < 40  → "低活跃"

    参数：三个指数（学习、活跃、互动）
    返回：表示状态的文字
    """

    # 计算三个指数的平均分
    average = (study_index + activity_index + interaction_index) / 3

    # 根据平均分判断状态
    if average >= 70:
        return "积极"
    elif average >= 40:
        return "一般"
    else:
        return "低活跃"


def infer_user_state(user_data, historical_records):
    """
    根据主观评分、当日行为和近期历史推断用户状态。

    这里使用透明、可解释的规则，而不是假装成医学诊断或黑盒 AI。
    返回的结果可直接交给上层桌宠界面使用。
    """

    mood = user_data["mood"]
    energy = user_data["energy"]
    stress = user_data["stress"]
    reasons = []

    # 压力优先级最高；其次是明显疲惫；状态良好时判断为充实
    if stress >= 4:
        state = "压力偏高"
        reasons.append(f"今日压力评分为 {stress}/5")
    elif energy <= 2:
        state = "疲惫"
        reasons.append(f"今日精力评分仅为 {energy}/5")
    elif mood >= 4 and energy >= 4 and stress <= 2:
        state = "充实"
        reasons.append("心情和精力较好，且当前压力较低")
    else:
        state = "平稳"
        reasons.append("今日各项主观状态处于正常波动范围")

    # 补充当日行为依据，让结果不只依赖一次主观评分
    if user_data["study_hours"] >= 6 and energy <= 3:
        reasons.append("学习时间较长，同时精力偏低")
    if user_data["tasks_completed"] >= 3 and mood >= 3:
        reasons.append("今日完成了多项任务")

    # 旧版记录没有三个主观字段，因此只使用字段完整的近期记录
    valid_history = [
        record for record in historical_records
        if all(key in record for key in ("mood", "energy", "stress"))
    ]
    valid_history.sort(key=lambda record: record.get("date", ""))
    recent_history = valid_history[-3:]

    if recent_history:
        avg_energy = sum(record["energy"] for record in recent_history) / len(recent_history)
        avg_stress = sum(record["stress"] for record in recent_history) / len(recent_history)

        if energy <= avg_energy - 1:
            reasons.append("今日精力比近期平均水平明显下降")
        if stress >= avg_stress + 1:
            reasons.append("今日压力比近期平均水平明显上升")

    response_table = {
        "压力偏高": {
            "pet_reaction": "comfort",
            "recommendation": {
                "type": "relax",
                "title": "进行十分钟放松",
                "difficulty": 1
            }
        },
        "疲惫": {
            "pet_reaction": "rest",
            "recommendation": {
                "type": "rest",
                "title": "暂时离开屏幕休息二十分钟",
                "difficulty": 1
            }
        },
        "充实": {
            "pet_reaction": "celebrate",
            "recommendation": {
                "type": "review",
                "title": "记录一件今天最有成就感的事",
                "difficulty": 1
            }
        },
        "平稳": {
            "pet_reaction": "encourage",
            "recommendation": {
                "type": "focus",
                "title": "完成一次二十五分钟专注任务",
                "difficulty": 2
            }
        }
    }

    result = response_table[state]
    return {
        "state": state,
        "reasons": reasons,
        "pet_reaction": result["pet_reaction"],
        "recommendation": result["recommendation"]
    }


# ============================================================
# 第三部分：数据存储
# ============================================================

def find_today_index(records, today):
    """
    在历史记录列表中查找今天是否已经有记录。

    参数：
    - records - 所有历史记录组成的列表
    - today - 今天的日期字符串，例如 "2026-08-25"

    返回：
    - 如果今天已有记录：返回它在列表中的位置（从 0 开始数）
    - 如果今天没有记录：返回 -1
    """

    # 用循环逐条检查每条记录的日期
    for i in range(len(records)):

        # 这条记录的日期和今天相同，说明今天已经有记录了
        if records[i].get("date") == today:
            return i

    # 循环结束都没找到，返回 -1 表示今天没有记录
    return -1


def load_data():
    """
    从 JSON 文件中加载历史数据。

    如果数据文件不存在（第一次运行），返回一个空的记录列表。
    如果文件已存在，读取并返回其中的数据。

    返回：一个字典，格式为 {"records": [...], "pet": {...}}
    """

    # 检查数据文件是否存在
    # os.path.exists() 会返回 True 或 False
    if not os.path.exists(DATA_FILE):
        # 文件不存在，说明是第一次运行
        # 返回一个包含空记录列表的字典
        return {"records": []}

    # 文件存在，读取它。损坏时停止运行，避免覆盖原文件。
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        print(f"数据文件读取失败：{error}")
        print("为保护已有数据，本次不会继续保存。")
        return None

    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        print("数据文件格式无效：缺少 records 列表。")
        print("为保护已有数据，本次不会继续保存。")
        return None

    return data


def save_data(data):
    """
    将数据保存到 JSON 文件。

    如果 data 目录不存在，会自动创建。
    保存时会保留所有历史记录（追加，不覆盖）。

    参数：data - 要保存的数据字典
    """

    # 检查 data 目录是否存在，不存在就创建
    # os.makedirs 可以一次性创建多级目录
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 先写临时文件，再原子替换正式文件。
    # 即使写入过程中断，也不容易破坏上一份有效数据。
    temporary_file = DATA_FILE + ".tmp"
    with open(temporary_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temporary_file, DATA_FILE)


# ============================================================
# 第四部分：历史数据分析（V0.2 新增）
# ============================================================

def calculate_historical_statistics(records):
    """
    计算所有历史记录的平均值统计。

    统计内容包括：
    - 累计记录天数
    - 平均学习时间、平均游戏时间
    - 平均完成任务数、平均互动次数
    - 平均学习指数、平均活跃指数、平均互动指数

    参数：records - 所有历史记录组成的列表

    返回：一个字典，包含记录天数和各项平均值
    """

    # 记录的天数就是列表的长度
    total_days = len(records)

    # 准备累加变量，初始值都是 0
    total_study_hours = 0
    total_game_minutes = 0
    total_tasks = 0
    total_interactions = 0
    total_study_index = 0
    total_activity_index = 0
    total_interaction_index = 0

    # 用循环把每一条记录的数据累加起来
    for record in records:
        total_study_hours += record["study_hours"]
        total_game_minutes += record["game_minutes"]
        total_tasks += record["tasks_completed"]
        total_interactions += record["interactions"]
        total_study_index += record["study_index"]
        total_activity_index += record["activity_index"]
        total_interaction_index += record["interaction_index"]

    # 累加的总和除以天数，得到各项平均值
    # 再把所有统计结果整理成一个字典返回
    statistics = {
        "total_days": total_days,
        "avg_study_hours": total_study_hours / total_days,
        "avg_game_minutes": total_game_minutes / total_days,
        "avg_tasks_completed": total_tasks / total_days,
        "avg_interactions": total_interactions / total_days,
        "avg_study_index": total_study_index / total_days,
        "avg_activity_index": total_activity_index / total_days,
        "avg_interaction_index": total_interaction_index / total_days
    }

    return statistics


def calculate_consecutive_days(records):
    """
    计算连续记录了多少天。

    注意：这里按"日期是否连续"来计算，
    而不是简单地数记录的条数。

    例如记录日期是 8/23、8/24、8/25，
    连续记录天数就是 3 天。
    如果日期是 8/23、8/25（中间断了 8/24），
    连续天数只算 1 天（从最近的 8/25 往前看）。

    参数：records - 所有历史记录（按时间先后排列，最后一条最近）

    返回：连续记录的天数
    """

    # 没有任何记录，连续天数是 0
    if len(records) == 0:
        return 0

    # 使用排序后的副本，不修改原列表，也不依赖文件中的原有顺序
    ordered_records = sorted(records, key=lambda record: record["date"])

    # 连续天数先记为 1，代表最近这一天的记录
    consecutive = 1

    # i 是当前检查的记录下标，从最后一条（最近的一天）开始
    i = len(ordered_records) - 1

    # 只要前面还有记录，就继续往前检查
    while i >= 1:

        # 把当前这条记录的日期文字，转换成日期对象
        # strptime 的意思是：按 "%Y-%m-%d" 的格式解读文字
        current_date = datetime.strptime(ordered_records[i]["date"], "%Y-%m-%d").date()

        # 把前一条记录的日期文字，也转换成日期对象
        previous_date = datetime.strptime(ordered_records[i - 1]["date"], "%Y-%m-%d").date()

        # 两个日期相减，得到相差的天数
        difference = (current_date - previous_date).days

        if difference == 1:
            # 正好相差 1 天，说明日期连续，连续天数加 1
            consecutive += 1
            # 继续往前检查更早的一条记录
            i -= 1
        else:
            # 日期断开了（相差超过 1 天），停止往前检查
            break

    return consecutive


def calculate_trend(records, field_name):
    """
    分析某个指数的变化趋势。

    比较方法：
    - 取最近 3 天记录的平均值
    - 取此前所有记录的平均值
    - 比较两者相差多少

    趋势判断（差值超过 TREND_THRESHOLD 分才算明显变化）：
    - 最近 3 天明显更高 → "↑"
    - 最近 3 天明显更低 → "↓"
    - 变化不明显       → "→"

    参数：
    - records - 所有历史记录（按时间先后排列）
    - field_name - 要分析的指数字段名，如 "study_index"

    返回："↑"、"↓"、"→"，或者 None（记录不足，无法分析）
    """

    # 趋势分析至少需要 4 条记录：
    # 最近 3 条 + 此前至少 1 条
    # 记录不足时返回 None，表示无法分析
    if len(records) < 4:
        return None

    # 使用排序后的副本，确保列表末尾确实是最近记录
    ordered_records = sorted(records, key=lambda record: record["date"])

    # 记录按时间先后排列，列表末尾是最近的记录
    # records[-3:] 表示"列表最后 3 条"，也就是最近 3 天的记录
    recent_records = ordered_records[-3:]

    # records[:-3] 表示"去掉最后 3 条后剩下的"，也就是此前的记录
    earlier_records = ordered_records[:-3]

    # 计算最近 3 天的平均值
    recent_total = 0
    for record in recent_records:
        recent_total += record[field_name]
    recent_average = recent_total / len(recent_records)

    # 计算此前的平均值
    earlier_total = 0
    for record in earlier_records:
        earlier_total += record[field_name]
    earlier_average = earlier_total / len(earlier_records)

    # 差值 = 最近 3 天的平均值 - 此前的平均值
    difference = recent_average - earlier_average

    # 根据差值判断趋势方向
    if difference > TREND_THRESHOLD:
        return "↑"
    elif difference < -TREND_THRESHOLD:
        return "↓"
    else:
        return "→"


def show_historical_analysis(records):
    """
    显示"历史表现分析"区域。

    包含三部分内容：
    1. 平均值统计（学习时间、游戏时间、指数等）
    2. 连续记录天数
    3. 三个指数的趋势分析（↑ / ↓ / →）

    参数：records - 所有历史记录（包含今天刚保存的记录）
    """

    print()
    print("=" * 40)
    print("       历史表现分析")
    print("=" * 40)

    # 没有任何记录时，直接返回
    # （正常流程不会出现，这里只是保护一下）
    if len(records) == 0:
        print("暂时没有历史数据。")
        return

    # ---- 第一部分：平均值统计 ----
    statistics = calculate_historical_statistics(records)

    print(f"累计记录天数：{statistics['total_days']}")
    print(f"连续记录天数：{calculate_consecutive_days(records)}")
    print()
    print(f"平均学习时间：{statistics['avg_study_hours']:.1f} 小时")
    print(f"平均游戏时间：{statistics['avg_game_minutes']:.1f} 分钟")
    print(f"平均完成任务：{statistics['avg_tasks_completed']:.1f} 个")
    print(f"平均互动次数：{statistics['avg_interactions']:.1f} 次")
    print(f"平均学习指数：{statistics['avg_study_index']:.1f}")
    print(f"平均活跃指数：{statistics['avg_activity_index']:.1f}")
    print(f"平均互动指数：{statistics['avg_interaction_index']:.1f}")

    # ---- 第二部分：趋势分析 ----
    # 三个指数分别计算趋势
    study_trend = calculate_trend(records, "study_index")
    activity_trend = calculate_trend(records, "activity_index")
    interaction_trend = calculate_trend(records, "interaction_index")

    print()

    if study_trend is None:
        # 记录不足 4 天，无法做趋势比较
        # 不报错，只给出提示（平均值在上面已经正常显示）
        print("历史数据不足，暂时无法分析趋势（需要至少 4 天记录）")
    else:
        # 显示三个指数的趋势箭头
        print(f"学习趋势：{study_trend}")
        print(f"活跃趋势：{activity_trend}")
        print(f"互动趋势：{interaction_trend}")

    print("=" * 40)


# ============================================================
# 第五部分：长期用户画像（V0.5 新增）
# ============================================================

def calculate_field_average(records, field_name):
    """计算记录中某个数值字段的平均值，缺失或无效字段会被忽略。"""

    values = []
    for record in records:
        value = record.get(field_name)
        if isinstance(value, (int, float)) and math.isfinite(value):
            values.append(value)

    if not values:
        return None

    return round(sum(values) / len(values), 2)


def find_dominant_state(records):
    """统计最常出现的综合状态；并列时采用最近一次出现的状态。"""

    allowed_states = {"充实", "平稳", "疲惫", "压力偏高"}
    state_counts = {}

    for record in records:
        state = record.get("inferred_state")
        if state in allowed_states:
            state_counts[state] = state_counts.get(state, 0) + 1

    if not state_counts:
        return None, {}

    highest_count = max(state_counts.values())
    for record in reversed(records):
        state = record.get("inferred_state")
        if state_counts.get(state) == highest_count:
            return state, state_counts

    return None, state_counts


def build_user_profile(records, updated_at):
    """
    根据历史记录重新生成长期用户画像。

    画像是 records 的派生结果，不做增量累加。因此覆盖旧记录时，
    只要再次调用本函数，画像就会自然修正，不需要额外“扣除画像”。
    """

    ordered_records = sorted(records, key=lambda record: record.get("date", ""))
    recent_records = ordered_records[-7:]
    subjective_records = [
        record for record in ordered_records
        if all(
            isinstance(record.get(key), (int, float))
            and math.isfinite(record[key])
            for key in ("mood", "energy", "stress")
        )
    ]
    recent_subjective_records = [
        record for record in recent_records
        if all(
            isinstance(record.get(key), (int, float))
            and math.isfinite(record[key])
            for key in ("mood", "energy", "stress")
        )
    ]

    subjective_days = len(subjective_records)
    if subjective_days < 3:
        maturity = "数据积累中"
    elif subjective_days < 7:
        maturity = "画像形成中"
    else:
        maturity = "画像较稳定"

    dominant_state, state_distribution = find_dominant_state(ordered_records)

    long_term = {
        "avg_study_hours": calculate_field_average(ordered_records, "study_hours"),
        "avg_game_minutes": calculate_field_average(ordered_records, "game_minutes"),
        "avg_tasks_completed": calculate_field_average(ordered_records, "tasks_completed"),
        "avg_interactions": calculate_field_average(ordered_records, "interactions"),
        "avg_mood": calculate_field_average(subjective_records, "mood"),
        "avg_energy": calculate_field_average(subjective_records, "energy"),
        "avg_stress": calculate_field_average(subjective_records, "stress"),
        "dominant_state": dominant_state
    }

    recent = {
        "window_size": len(recent_records),
        "avg_study_hours": calculate_field_average(recent_records, "study_hours"),
        "avg_tasks_completed": calculate_field_average(recent_records, "tasks_completed"),
        "avg_interactions": calculate_field_average(recent_records, "interactions"),
        "avg_mood": calculate_field_average(recent_subjective_records, "mood"),
        "avg_energy": calculate_field_average(recent_subjective_records, "energy"),
        "avg_stress": calculate_field_average(recent_subjective_records, "stress")
    }

    traits = []
    if subjective_days < 3:
        traits.append("画像数据仍在积累")
    else:
        if (long_term["avg_study_hours"] is not None
                and long_term["avg_study_hours"] >= 4):
            traits.append("学习投入较高")
        elif (long_term["avg_study_hours"] is not None
              and long_term["avg_study_hours"] <= 1):
            traits.append("偏好轻量学习节奏")

        if (long_term["avg_tasks_completed"] is not None
                and long_term["avg_tasks_completed"] >= 3):
            traits.append("任务执行力较强")

        if (long_term["avg_interactions"] is not None
                and long_term["avg_interactions"] >= 5):
            traits.append("乐于与桌宠互动")
        elif (long_term["avg_interactions"] is not None
              and long_term["avg_interactions"] <= 1):
            traits.append("更偏好低频陪伴")

        if (long_term["avg_stress"] is not None
                and long_term["avg_stress"] >= 3.8):
            traits.append("长期压力水平偏高")
        if (long_term["avg_energy"] is not None
                and long_term["avg_energy"] <= 2.5):
            traits.append("精力恢复可能不足")
        if (long_term["avg_mood"] is not None
                and long_term["avg_mood"] >= 4):
            traits.append("整体心情较积极")

    recent_stress = recent["avg_stress"]
    recent_energy = recent["avg_energy"]
    recent_mood = recent["avg_mood"]

    if subjective_days < 3:
        care_strategy = {
            "mode": "observe",
            "preferred_reaction": "encourage",
            "task_difficulty": 1,
            "message": "继续温和记录，暂不根据少量数据下长期结论"
        }
    elif recent_stress is not None and recent_stress >= 3.8:
        care_strategy = {
            "mode": "reduce_load",
            "preferred_reaction": "comfort",
            "task_difficulty": 1,
            "message": "近期压力偏高，优先推荐低负担放松任务"
        }
    elif recent_energy is not None and recent_energy <= 2.5:
        care_strategy = {
            "mode": "recovery",
            "preferred_reaction": "rest",
            "task_difficulty": 1,
            "message": "近期精力偏低，优先保证休息和恢复"
        }
    elif (recent_mood is not None and recent_mood >= 4
          and recent_energy is not None and recent_energy >= 3.5):
        care_strategy = {
            "mode": "growth",
            "preferred_reaction": "celebrate",
            "task_difficulty": 3,
            "message": "近期状态良好，可以推荐适度挑战型成长任务"
        }
    else:
        care_strategy = {
            "mode": "steady",
            "preferred_reaction": "encourage",
            "task_difficulty": 2,
            "message": "保持当前节奏，提供稳定且适量的日常任务"
        }

    if subjective_days < 3:
        summary = f"已积累 {subjective_days}/3 天主观状态数据，画像正在形成"
    elif traits:
        summary = "；".join(traits[:3])
    else:
        summary = "长期数据整体较为均衡"

    return {
        "version": 1,
        "updated_at": updated_at,
        "sample_size": {
            "total_days": len(ordered_records),
            "subjective_days": subjective_days
        },
        "maturity": maturity,
        "summary": summary,
        "traits": traits,
        "state_distribution": state_distribution,
        "long_term": long_term,
        "recent_7_records": recent,
        "care_strategy": care_strategy
    }


def apply_profile_to_recommendation(record, profile):
    """把长期画像策略附加到今日建议中，供上层界面直接读取。"""

    recommendation = record["recommendation"]
    strategy = profile["care_strategy"]
    recommendation["profile_context"] = strategy["message"]

    # 压力或疲惫状态下只降低难度，不用长期画像强行增加任务负担
    if record["inferred_state"] in ("压力偏高", "疲惫"):
        recommendation["difficulty"] = min(
            recommendation["difficulty"], strategy["task_difficulty"]
        )
    elif profile["maturity"] != "数据积累中":
        recommendation["difficulty"] = strategy["task_difficulty"]


def show_user_profile(profile):
    """在命令行显示长期用户画像摘要。"""

    print()
    print("=" * 40)
    print("       长期用户画像")
    print("=" * 40)
    print(f"画像成熟度：{profile['maturity']}")
    print(f"累计样本：{profile['sample_size']['total_days']} 天")
    print(f"主观状态样本：{profile['sample_size']['subjective_days']} 天")
    print(f"画像摘要：{profile['summary']}")

    long_term = profile["long_term"]
    if long_term["dominant_state"] is not None:
        print(f"长期主导状态：{long_term['dominant_state']}")
    if long_term["avg_mood"] is not None:
        print(f"长期平均心情：{long_term['avg_mood']:.1f} / 5")
        print(f"长期平均精力：{long_term['avg_energy']:.1f} / 5")
        print(f"长期平均压力：{long_term['avg_stress']:.1f} / 5")

    if profile["traits"]:
        print("画像标签：" + "、".join(profile["traits"]))

    strategy = profile["care_strategy"]
    print(f"陪伴模式：{strategy['mode']}")
    print(f"陪伴策略：{strategy['message']}")
    print("=" * 40)


# ============================================================
# 第六部分：桌宠成长系统（V0.3 新增）
# ============================================================

def calculate_daily_xp(record, consecutive_days):
    """
    计算某一天的记录能为桌宠带来多少 XP（经验值）。

    规则（数值集中在顶部的 XP_RULES 字典里）：
    - 每完成 1 个任务：+10 XP
    - 学习时间每满 1 小时：+5 XP（不足 1 小时的部分不算）
    - 每与桌宠互动 1 次：+2 XP
    - 当日学习指数达到 70：额外 +10 XP
    - 当日连续记录达到 3 天：额外 +10 XP

    参数：
    - record - 一条完整的每日记录（字典）
    - consecutive_days - 当天的连续记录天数（包含当天）

    返回：这一天获得的 XP（整数）
    """

    # 从记录中取出需要用到的数据
    study_hours = record["study_hours"]
    tasks_completed = record["tasks_completed"]
    interactions = record["interactions"]
    study_index = record["study_index"]

    # 1. 任务 XP：每个任务 10 点
    xp = tasks_completed * XP_RULES["per_task"]

    # 2. 学习 XP：每满 1 小时 5 点
    # int() 会直接去掉小数部分，例如 2.5 小时只算 2 个整小时
    xp += int(study_hours) * XP_RULES["per_study_hour"]

    # 3. 互动 XP：每次互动 2 点
    xp += interactions * XP_RULES["per_interaction"]

    # 4. 学习指数奖励：指数达到 70 时额外 10 点
    if study_index >= XP_RULES["study_index_threshold"]:
        xp += XP_RULES["study_index_bonus"]

    # 5. 连续记录奖励：连续天数达到 3 天时额外 10 点
    if consecutive_days >= XP_RULES["streak_bonus_days"]:
        xp += XP_RULES["streak_bonus"]

    return xp


def calculate_level(total_xp):
    """
    根据累计 XP 计算桌宠当前等级。

    等级规则（数值集中在顶部的 LEVEL_TABLE 列表里）：
    - 0 ~ 99 XP    → Lv.1
    - 100 ~ 199 XP → Lv.2
    - 200 ~ 349 XP → Lv.3
    - 350 ~ 499 XP → Lv.4
    - 500 ~ 699 XP → Lv.5
    - 700 XP 以上   → Lv.6+

    参数：total_xp - 桌宠的累计经验值
    返回：等级数字（1 ~ 6）
    """

    # 先假设是最低等级 1 级
    level = 1

    # 从头到尾遍历等级表：
    # 只要累计 XP 达到某一行的门槛，就把等级更新成那一行的等级
    # 因为等级表从低到高排列，最后命中的那一行就是最终等级
    for min_xp, table_level in LEVEL_TABLE:
        if total_xp >= min_xp:
            level = table_level

    return level


def get_level_text(level):
    """
    把等级数字转换成显示用的文字。

    1 ~ 5 级显示成 Lv.1 ~ Lv.5，
    6 级显示成 Lv.6+（表示 6 级及以上）。

    参数：level - 等级数字
    返回：例如 "Lv.3"、"Lv.6+"
    """

    if level >= 6:
        return "Lv.6+"

    return "Lv." + str(level)


def calculate_daily_intimacy(record):
    """
    计算某一天的记录能增加多少亲密度。

    规则（数值集中在顶部的 INTIMACY_RULES 字典里）：
    - 每与桌宠互动 1 次：+1
    - 每完成 1 个任务：+1
    - 每天成功记录数据：+1
    - 当日学习指数达到 70：额外 +2

    亲密度总量会由 update_pet_data() 限制在 0 ~ 100 之间。

    参数：record - 一条完整的每日记录（字典）

    返回：这一天增加的亲密度（整数）
    """

    # "每天成功记录数据 +1"：只要这条记录存在，就加这 1 点
    intimacy = INTIMACY_RULES["daily_record"]

    # 互动加分：每次互动 1 点
    intimacy += record["interactions"] * INTIMACY_RULES["per_interaction"]

    # 任务加分：每个任务 1 点
    intimacy += record["tasks_completed"] * INTIMACY_RULES["per_task"]

    # 学习指数达标奖励：额外 2 点
    if record["study_index"] >= INTIMACY_RULES["study_index_threshold"]:
        intimacy += INTIMACY_RULES["study_index_bonus"]

    return intimacy


def load_pet_data(data):
    """
    从数据字典中获取桌宠数据。

    兼容旧版本的数据文件：
    - 旧文件只有 records，没有 pet 字段
    - 遇到这种情况，自动创建一份默认的 pet 数据（全部从 0 开始）
    - 已有的 records 数据完全不受影响

    参数：data - 完整的数据字典（包含 records）

    返回：桌宠数据字典 {"xp": ..., "level": ..., "intimacy": ...}
    """

    # 检查数据里有没有 pet 字段
    if "pet" not in data:
        # 没有：这是旧版本的数据文件，创建默认的桌宠数据
        data["pet"] = {
            "xp": 0,        # 累计经验值
            "level": 1,     # 当前等级
            "intimacy": 0   # 亲密度（0 ~ 100）
        }

    return data["pet"]


def update_pet_data(pet, xp_change, intimacy_change):
    """
    更新桌宠的 XP、等级和亲密度。

    参数：
    - pet - 桌宠数据字典（会被直接修改）
    - xp_change - XP 变化量（正数增加，负数减少）
    - intimacy_change - 亲密度变化量（正数增加，负数减少）

    返回：(更新前的等级, 更新后的等级)
    主程序用这两个值判断要不要显示升级提示。
    """

    # 先根据旧 XP 算出更新前的等级
    old_level = calculate_level(pet["xp"])

    # 更新累计 XP（XP 不允许小于 0）
    pet["xp"] += xp_change
    if pet["xp"] < 0:
        pet["xp"] = 0

    # 根据新 XP 重新计算等级，并保存到桌宠数据里
    new_level = calculate_level(pet["xp"])
    pet["level"] = new_level

    # 更新亲密度（亲密度限制在 0 ~ 100 之间）
    pet["intimacy"] += intimacy_change
    if pet["intimacy"] > INTIMACY_RULES["max"]:
        pet["intimacy"] = INTIMACY_RULES["max"]
    if pet["intimacy"] < 0:
        pet["intimacy"] = 0

    return old_level, new_level


def show_pet_status(pet, daily_xp_change, daily_intimacy_change,
                    old_level, new_level, is_correction=False):
    """
    显示"桌宠状态"区域。

    显示内容：
    - 等级、经验值、亲密度（亲密度后面带今日变化）
    - 今日获得的 XP
    - 如果这次运行让桌宠升级了，显示升级提示

    参数：
    - pet - 桌宠数据字典
    - daily_xp_change - 今日 XP 变化量
    - daily_intimacy_change - 今日亲密度变化量
    - old_level / new_level - 更新前后的等级
    """

    print()
    print("-" * 40)
    print("       桌宠状态")
    print("-" * 40)
    print(f"等级：{get_level_text(pet['level'])}")
    print(f"经验值：{pet['xp']} XP")

    # 亲密度后面的（+4）表示今天增加的数量
    # {:+d} 的意思是：正数前面带 + 号，负数前面带 - 号
    print(f"亲密度：{pet['intimacy']} / {INTIMACY_RULES['max']}"
          f"（{daily_intimacy_change:+d}）")

    print()
    if is_correction:
        print(f"本次数据修正：{daily_xp_change:+d} XP")
    else:
        print(f"今日获得 XP：{daily_xp_change}")

    # 更新后的等级数字比更新前大，说明这次运行升级了
    if new_level > old_level:
        print()
        print("恭喜！桌宠升级了！")
        print(f"{get_level_text(old_level)} → {get_level_text(new_level)}")

    print("-" * 40)


# ============================================================
# 第七部分：主程序
# ============================================================

def pause_before_exit():
    """
    在程序退出前暂停一下。

    这样可以解决"程序运行结束后窗口立即关闭"的问题：
    用户可以慢慢看屏幕上的分析结果，
    按 Enter 键之后程序才会真正退出。
    """

    input("\n按 Enter 键退出...")


def main():
    """
    主函数：程序的入口。

    执行流程：
    1. 获取用户输入（带合法性检查）
    2. 计算三个指标
    3. 加载历史数据，推断今日综合状态
    4. 整理今天的完整记录
    5. 加载桌宠数据
    6. 如果今天已有记录，询问用户是否覆盖
    7. 根据全部记录重新生成长期用户画像
    8. 计算今日 XP 和亲密度，更新桌宠成长数据
    9. 保存行为、桌宠与用户画像数据
    10. 显示今日分析、桌宠状态、历史分析和长期画像
    11. 暂停，等用户按 Enter 键再退出
    """

    # ---- 第一步：获取用户输入 ----
    user_data = get_user_input()

    # ---- 第二步：计算三个指标 ----
    study_index = calculate_study_index(user_data["study_hours"])
    activity_index = calculate_activity_index(
        user_data["game_minutes"],
        user_data["tasks_completed"]
    )
    interaction_index = calculate_interaction_index(user_data["interactions"])

    # ---- 第三步：加载历史数据并推断状态 ----
    # 原有三个指数得到的是“行为活跃状态”；V0.4 的综合状态还会结合
    # 心情、精力、压力及近期记录，两者分别保存，避免概念混淆。
    behavior_status = determine_status(
        study_index, activity_index, interaction_index
    )

    # 获取今天的日期，格式如 "2026-08-25"
    today = datetime.now().strftime("%Y-%m-%d")

    data = load_data()
    if data is None:
        pause_before_exit()
        return

    records = data["records"]
    today_index = find_today_index(records, today)

    # 覆盖时不能把旧的“今天”当成历史依据，否则会重复比较自己
    historical_records = [
        record for record in records if record.get("date") != today
    ]
    state_result = infer_user_state(user_data, historical_records)

    # ---- 第四步：整理今天的完整记录 ----
    # 把原始数据和计算结果整理成一条完整记录
    today_record = {
        "date": today,
        "study_hours": user_data["study_hours"],
        "game_minutes": user_data["game_minutes"],
        "tasks_completed": user_data["tasks_completed"],
        "interactions": user_data["interactions"],
        "mood": user_data["mood"],
        "energy": user_data["energy"],
        "stress": user_data["stress"],
        "study_index": study_index,
        "activity_index": activity_index,
        "interaction_index": interaction_index,
        "status": behavior_status,
        "inferred_state": state_result["state"],
        "state_reasons": state_result["reasons"],
        "recommendation": state_result["recommendation"],
        "pet_reaction": state_result["pet_reaction"]
    }

    # ---- 第五步：加载历史数据和桌宠数据 ----
    # 获取桌宠数据
    # 如果是旧版本数据文件（没有 pet 字段），会自动创建默认数据
    pet = load_pet_data(data)

    # 记录"覆盖前的旧记录"
    # 覆盖时需要先扣掉旧记录对应的成长值，再加上新数据的，
    # 这样同一天反复覆盖也不会"刷"XP 和亲密度
    old_record = None

    if today_index != -1:
        # 今天已经有记录了，询问用户怎么处理
        print(f"提示：今天（{today}）已经有一条记录。")
        answer = ask_yes_no("是否用新数据覆盖今天的记录？")

        if not answer:
            # 用户选择"否"：不覆盖，直接退出
            # 没有保存任何数据，不会产生重复记录
            print("已取消，今天的记录保持不变。")
            pause_before_exit()
            return

        # 用户选择"是"：
        # 先把旧记录保存下来（一会儿要按它扣减成长值）
        old_record = records[today_index]
        # 再用新记录替换今天的旧记录
        records[today_index] = today_record
    else:
        # 今天还没有记录，正常追加新记录
        records.append(today_record)

    # ---- 第六步：重新生成长期用户画像 ----
    # 画像完全由 records 推导，所以新增与覆盖使用同一套逻辑。
    user_profile = build_user_profile(records, today)
    data["user_profile"] = user_profile
    apply_profile_to_recommendation(today_record, user_profile)

    # ---- 第七步：计算 XP 和亲密度，更新桌宠成长数据 ----
    # 计算连续记录天数（此时今天的记录已经加入列表）
    consecutive_days = calculate_consecutive_days(records)

    # 计算今天的记录能带来多少 XP 和亲密度
    today_xp = calculate_daily_xp(today_record, consecutive_days)
    today_intimacy = calculate_daily_intimacy(today_record)

    if old_record is not None:
        # 覆盖场景：把旧记录对应的 XP 和亲密度算出来并扣掉
        # 差值 = 新记录的成长值 - 旧记录的成长值
        old_xp = calculate_daily_xp(old_record, consecutive_days)
        old_intimacy = calculate_daily_intimacy(old_record)
        xp_change = today_xp - old_xp
        intimacy_change = today_intimacy - old_intimacy
    else:
        # 新增场景：成长值就是今天获得的量
        xp_change = today_xp
        intimacy_change = today_intimacy

    # 记录更新前的 XP 和亲密度，一会儿用来算"今日实际变化"
    # （亲密度达到上限 100 时，实际变化会小于理论值）
    xp_before = pet["xp"]
    intimacy_before = pet["intimacy"]

    # 更新桌宠的 XP、等级、亲密度
    old_level, new_level = update_pet_data(pet, xp_change, intimacy_change)

    # 今日实际变化 = 更新后的值 - 更新前的值
    daily_xp_change = pet["xp"] - xp_before
    daily_intimacy_change = pet["intimacy"] - intimacy_before

    # ---- 第八步：保存行为、桌宠和画像数据 ----
    save_data(data)

    # ---- 第九步：显示今日分析结果 ----
    print("=" * 40)
    print("       今日分析结果")
    print("=" * 40)
    print(f"学习指数：{study_index}")
    print(f"活跃指数：{activity_index}")
    print(f"互动指数：{interaction_index}")
    print(f"行为活跃状态：{behavior_status}")
    print()
    print(f"今日心情：{user_data['mood']} / 5")
    print(f"今日精力：{user_data['energy']} / 5")
    print(f"今日压力：{user_data['stress']} / 5")
    print(f"综合状态：{state_result['state']}")
    print("判断依据：")
    for reason in state_result["reasons"]:
        print(f"  - {reason}")
    print(f"今日建议：{state_result['recommendation']['title']}")
    print(f"画像参考：{state_result['recommendation']['profile_context']}")
    print(f"桌宠反应：{state_result['pet_reaction']}")
    print("=" * 40)

    # 根据刚才的处理方式，给用户一个明确的提示
    if today_index != -1:
        print("今天的记录已更新（覆盖了旧数据）。")
    else:
        print("今天的记录已保存（新增一条）。")

    print(f"数据文件：{DATA_FILE}")
    print(f"累计记录天数：{len(data['records'])}")

    # ---- 第十步：显示桌宠状态（V0.3 新增）----
    show_pet_status(pet, daily_xp_change, daily_intimacy_change,
                    old_level, new_level,
                    is_correction=(old_record is not None))

    # ---- 第十一步：显示历史表现分析和长期画像 ----
    show_historical_analysis(data["records"])
    show_user_profile(user_profile)

    # ---- 第十二步：暂停，等用户按 Enter 键再退出 ----
    pause_before_exit()


# ============================================================
# 程序入口
# ============================================================

# 这行代码的意思是：只有直接运行本文件时，才会执行 main()
# 如果本文件被其他文件 import，不会自动执行 main()
if __name__ == "__main__":
    main()
