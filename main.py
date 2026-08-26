"""
DigitalLifeEngine - 数字生命引擎
V0.3：每日行为记录与分析 + 历史数据分析 + 桌宠成长系统

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
"""


import json        # 用于读写 JSON 数据文件
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

def ask_positive_number(prompt, allow_decimal=True):
    """
    向用户询问一个数字，并做合法性检查。

    检查规则：
    1. 输入必须是数字（否则提示重新输入）
    2. 数字不能小于 0（否则提示重新输入）

    参数：
    - prompt - 提示文字，例如 "今天学习了几小时？ "
    - allow_decimal - True 表示允许小数（如 2.5），
                      False 表示只接受整数

    返回：一个合法的数字（大于等于 0）
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

        # 检查数字是否小于 0
        if number < 0:
            print("  数字不能小于 0，请重新输入。")
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

    会依次询问四个问题：
    1. 今天学习了几小时
    2. 今天玩游戏多少分钟
    3. 今天完成了几个任务
    4. 今天与桌宠互动了几次

    每个问题都会做合法性检查：
    - 输入非数字会提示重新输入
    - 输入负数会提示重新输入

    返回值：一个字典，包含四项数据
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

    print()

    # 把收集到的数据整理成字典，方便后续使用
    user_data = {
        "study_hours": study_hours,
        "game_minutes": game_minutes,
        "tasks_completed": tasks_completed,
        "interactions": interactions
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
        if records[i]["date"] == today:
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

    # 文件存在，读取它
    # encoding="utf-8" 确保中文不会乱码
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

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

    # 将数据写入 JSON 文件
    # ensure_ascii=False 让中文正常显示
    # indent=2 让文件内容有缩进，方便人类阅读
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

    # 连续天数先记为 1，代表最近这一天的记录
    consecutive = 1

    # i 是当前检查的记录下标，从最后一条（最近的一天）开始
    i = len(records) - 1

    # 只要前面还有记录，就继续往前检查
    while i >= 1:

        # 把当前这条记录的日期文字，转换成日期对象
        # strptime 的意思是：按 "%Y-%m-%d" 的格式解读文字
        current_date = datetime.strptime(records[i]["date"], "%Y-%m-%d").date()

        # 把前一条记录的日期文字，也转换成日期对象
        previous_date = datetime.strptime(records[i - 1]["date"], "%Y-%m-%d").date()

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

    # 记录按时间先后保存，列表末尾是最近的记录
    # records[-3:] 表示"列表最后 3 条"，也就是最近 3 天的记录
    recent_records = records[-3:]

    # records[:-3] 表示"去掉最后 3 条后剩下的"，也就是此前的记录
    earlier_records = records[:-3]

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
# 第五部分：桌宠成长系统（V0.3 新增）
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
                    old_level, new_level):
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
    print(f"今日获得 XP：{daily_xp_change}")

    # 更新后的等级数字比更新前大，说明这次运行升级了
    if new_level > old_level:
        print()
        print("恭喜！桌宠升级了！")
        print(f"{get_level_text(old_level)} → {get_level_text(new_level)}")

    print("-" * 40)


# ============================================================
# 第六部分：主程序
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
    3. 判断今日状态
    4. 整理今天的完整记录
    5. 加载历史数据和桌宠数据
    6. 如果今天已有记录，询问用户是否覆盖
    7. 计算今日 XP 和亲密度，更新桌宠成长数据
    8. 保存数据（行为记录和桌宠数据一起保存）
    9. 显示今日分析结果
    10. 显示桌宠状态（V0.3 新增）
    11. 显示历史表现分析
    12. 暂停，等用户按 Enter 键再退出
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

    # ---- 第三步：判断今日状态 ----
    status = determine_status(study_index, activity_index, interaction_index)

    # ---- 第四步：整理今天的完整记录 ----
    # 获取今天的日期，格式如 "2026-08-25"
    today = datetime.now().strftime("%Y-%m-%d")

    # 把原始数据和计算结果整理成一条完整记录
    today_record = {
        "date": today,
        "study_hours": user_data["study_hours"],
        "game_minutes": user_data["game_minutes"],
        "tasks_completed": user_data["tasks_completed"],
        "interactions": user_data["interactions"],
        "study_index": study_index,
        "activity_index": activity_index,
        "interaction_index": interaction_index,
        "status": status
    }

    # ---- 第五步：加载历史数据和桌宠数据 ----
    data = load_data()
    records = data["records"]

    # 获取桌宠数据
    # 如果是旧版本数据文件（没有 pet 字段），会自动创建默认数据
    pet = load_pet_data(data)

    # 查找今天的记录在列表中的位置
    # 返回 -1 表示今天还没有记录
    today_index = find_today_index(records, today)

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

    # ---- 第六步：计算 XP 和亲密度，更新桌宠成长数据 ----
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

    # ---- 第七步：保存数据（行为记录和桌宠数据一起保存）----
    save_data(data)

    # ---- 第八步：显示今日分析结果 ----
    print("=" * 40)
    print("       今日分析结果")
    print("=" * 40)
    print(f"学习指数：{study_index}")
    print(f"活跃指数：{activity_index}")
    print(f"互动指数：{interaction_index}")
    print(f"今日状态：{status}")
    print("=" * 40)

    # 根据刚才的处理方式，给用户一个明确的提示
    if today_index != -1:
        print("今天的记录已更新（覆盖了旧数据）。")
    else:
        print("今天的记录已保存（新增一条）。")

    print(f"数据文件：{DATA_FILE}")
    print(f"累计记录天数：{len(data['records'])}")

    # ---- 第九步：显示桌宠状态（V0.3 新增）----
    show_pet_status(pet, daily_xp_change, daily_intimacy_change,
                    old_level, new_level)

    # ---- 第十步：显示历史表现分析 ----
    show_historical_analysis(data["records"])

    # ---- 第十一步：暂停，等用户按 Enter 键再退出 ----
    pause_before_exit()


# ============================================================
# 程序入口
# ============================================================

# 这行代码的意思是：只有直接运行本文件时，才会执行 main()
# 如果本文件被其他文件 import，不会自动执行 main()
if __name__ == "__main__":
    main()
