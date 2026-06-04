"""
韩语日常素材库积累与主题作文智能生成工具
Korean Daily Material Corpus & Theme Essay Generator
支持本地规则生成 + DeepSeek AI 增强生成
支持自定义标题，可部署到 Railway 等云平台
"""
import json
import os
import random
import re
from datetime import datetime
from time import time
from functools import wraps

from openai import OpenAI
from flask import Flask, render_template, request, jsonify, send_file, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MATERIALS_FILE = os.path.join(DATA_DIR, "materials.json")
TEMPLATES_FILE = os.path.join(DATA_DIR, "templates.json")

# ==================== 预设场景分类 ====================
DEFAULT_CATEGORIES = [
    "日常问候", "饮食料理", "交通出行", "购物消费",
    "校园生活", "天气季节", "兴趣爱好", "旅游观光",
    "家庭生活", "健康医疗", "情感表达", "职场工作"
]

DIFFICULTY_LEVELS = ["初级", "中级", "高级"]


def load_json(filepath, default=None):
    if default is None:
        default = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_materials():
    data = load_json(MATERIALS_FILE, {"materials": [], "next_id": 1})
    if "next_id" not in data:
        data["next_id"] = max([m.get("id", 0) for m in data.get("materials", [])], default=0) + 1
    return data


def save_materials(data):
    save_json(MATERIALS_FILE, data)


def load_templates():
    return load_json(TEMPLATES_FILE, {"templates": []})


# ==================== 页面路由 ====================
@app.route("/")
def index():
    return render_template("index.html")


# ==================== 素材管理 API ====================
@app.route("/api/materials", methods=["GET"])
def get_materials():
    """获取所有素材，支持筛选"""
    data = load_materials()
    materials = data["materials"]

    category = request.args.get("category", "")
    difficulty = request.args.get("difficulty", "")
    search = request.args.get("search", "")
    tag = request.args.get("tag", "")

    if category:
        materials = [m for m in materials if m.get("category") == category]
    if difficulty:
        materials = [m for m in materials if m.get("difficulty") == difficulty]
    if search:
        kw = search.lower()
        materials = [m for m in materials if
                     kw in m.get("korean", "").lower() or
                     kw in m.get("chinese", "").lower() or
                     kw in m.get("example", "").lower()]
    if tag:
        materials = [m for m in materials if tag in m.get("tags", [])]

    return jsonify({"code": 0, "data": materials, "total": len(materials)})


@app.route("/api/materials", methods=["POST"])
def add_material():
    """新增素材"""
    data = load_materials()
    item = request.json

    required = ["korean", "chinese", "category"]
    for field in required:
        if not item.get(field):
            return jsonify({"code": 1, "msg": f"缺少必填字段: {field}"}), 400

    item["id"] = data["next_id"]
    data["next_id"] += 1
    item.setdefault("example", "")
    item.setdefault("example_cn", "")
    item.setdefault("difficulty", "初级")
    item.setdefault("tags", [])
    item.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    data["materials"].append(item)
    save_materials(data)
    return jsonify({"code": 0, "msg": "添加成功", "data": item})


@app.route("/api/materials/<int:mid>", methods=["PUT"])
def update_material(mid):
    """更新素材"""
    data = load_materials()
    for i, m in enumerate(data["materials"]):
        if m["id"] == mid:
            item = request.json
            item["id"] = mid
            data["materials"][i] = item
            save_materials(data)
            return jsonify({"code": 0, "msg": "更新成功"})
    return jsonify({"code": 1, "msg": "素材不存在"}), 404


@app.route("/api/materials/<int:mid>", methods=["DELETE"])
def delete_material(mid):
    """删除素材"""
    data = load_materials()
    data["materials"] = [m for m in data["materials"] if m["id"] != mid]
    save_materials(data)
    return jsonify({"code": 0, "msg": "删除成功"})


# ==================== 分类与统计 API ====================
@app.route("/api/categories", methods=["GET"])
def get_categories():
    """获取所有分类及素材数量"""
    data = load_materials()
    counts = {}
    for m in data["materials"]:
        cat = m.get("category", "未分类")
        counts[cat] = counts.get(cat, 0) + 1

    result = []
    for cat in DEFAULT_CATEGORIES:
        result.append({"name": cat, "count": counts.get(cat, 0)})
    for cat, cnt in counts.items():
        if cat not in DEFAULT_CATEGORIES:
            result.append({"name": cat, "count": cnt})
    return jsonify({"code": 0, "data": result})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """获取统计数据"""
    data = load_materials()
    materials = data["materials"]

    total = len(materials)

    diff_counts = {"初级": 0, "中级": 0, "高级": 0}
    for m in materials:
        d = m.get("difficulty", "初级")
        if d in diff_counts:
            diff_counts[d] += 1

    cat_counts = {}
    for m in materials:
        cat = m.get("category", "未分类")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    tag_counts = {}
    for m in materials:
        for tag in m.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    with_example = sum(1 for m in materials if m.get("example", "").strip())

    return jsonify({
        "code": 0,
        "data": {
            "total": total,
            "difficulty": diff_counts,
            "categories": cat_counts,
            "tags": tag_counts,
            "with_example": with_example,
            "with_example_rate": round(with_example / total * 100, 1) if total > 0 else 0
        }
    })


@app.route("/api/tags", methods=["GET"])
def get_all_tags():
    """获取所有标签"""
    data = load_materials()
    tags = set()
    for m in data["materials"]:
        for tag in m.get("tags", []):
            tags.add(tag)
    return jsonify({"code": 0, "data": sorted(list(tags))})


@app.route("/api/export", methods=["GET"])
def export_data():
    """导出全部数据为 JSON"""
    data = load_materials()
    export_path = os.path.join(DATA_DIR, "export_materials.json")
    save_json(export_path, data)
    return send_file(export_path, as_attachment=True,
                     download_name=f"韩语素材库_{datetime.now().strftime('%Y%m%d')}.json",
                     mimetype="application/json")


@app.route("/api/import", methods=["POST"])
def import_data():
    """导入 JSON 数据（合并模式）"""
    if "file" not in request.files:
        return jsonify({"code": 1, "msg": "请选择文件"}), 400

    file = request.files["file"]
    try:
        raw = file.read().decode("utf-8")
        imported = json.loads(raw)
    except Exception:
        return jsonify({"code": 1, "msg": "JSON 格式错误"}), 400

    current = load_materials()
    new_items = imported.get("materials", []) if isinstance(imported, dict) else imported

    existing_ids = {m["id"] for m in current["materials"]}
    added = 0
    for item in new_items:
        if item.get("id") in existing_ids:
            for i, m in enumerate(current["materials"]):
                if m["id"] == item["id"]:
                    current["materials"][i] = item
                    break
            existing_ids.discard(item["id"])
        else:
            item["id"] = current["next_id"]
            current["next_id"] += 1
            current["materials"].append(item)
            added += 1

    save_materials(current)
    return jsonify({"code": 0, "msg": f"导入完成：新增 {added} 条，共 {len(current['materials'])} 条素材"})


# ==================== 主题作文生成（固定主题，保留原功能） ====================
ESSAY_THEMES = {
    "자기소개": {
        "title_cn": "自我介绍",
        "categories": ["日常问候", "家庭生活", "兴趣爱好"],
        "structure": [
            {"type": "opening", "cn": "开场问候", "templates": [
                "안녕하세요! 저는 {name}이라고/라고 합니다.",
                "안녕하세요! 제 이름은 {name}입니다.",
                "여러분, 안녕하세요! 저는 {name}입니다.",
            ]},
            {"type": "body", "cn": "基本信息", "templates": [
                "저는 {age}살이고, {hometown}에서 왔습니다.",
                "저는 {hometown} 출신이고, 올해 {age}살입니다.",
                "저는 {hometown}에서 태어나서 지금까지 살고 있습니다.",
            ]},
            {"type": "body", "cn": "兴趣爱好", "templates": [
                "제 취미는 {hobby}입니다. {hobby_detail}",
                "저는 {hobby}을/를 좋아합니다. 특히 {hobby_detail}",
                "평소에 {hobby}을/를 즐겨 합니다. {hobby_detail}",
            ]},
            {"type": "closing", "cn": "结束语", "templates": [
                "앞으로 잘 부탁드립니다. 감사합니다!",
                "만나서 반갑습니다. 앞으로 잘 부탁해요!",
                "이상으로 제 소개를 마치겠습니다. 들어주셔서 감사합니다!",
            ]},
        ]
    },
    "나의_하루": {
        "title_cn": "我的一天",
        "categories": ["日常问候", "校园生活", "交通出行", "饮食料理"],
        "structure": [
            {"type": "opening", "cn": "开头", "templates": [
                "오늘은 제 하루에 대해 이야기해 보겠습니다.",
                "저의 평범한 하루를 소개하겠습니다.",
                "오늘 하루는 정말 {adjective} 하루였습니다.",
            ]},
            {"type": "body", "cn": "上午活动", "templates": [
                "아침 {time}시에 일어나서 {activity}을/를 합니다.",
                "아침을 먹고 {transport}을/를 타고 {place}에 갑니다.",
                "오전에는 주로 {morning_activity}을/를 하면서 시간을 보냅니다.",
            ]},
            {"type": "body", "cn": "下午活动", "templates": [
                "점심은 {lunch_place}에서 {food}을/를 먹었습니다.",
                "오후에는 {afternoon_activity}을/를 했습니다.",
                "{time}시쯤 {place}에서 친구와 함께 {activity}을/를 합니다.",
            ]},
            {"type": "closing", "cn": "结尾", "templates": [
                "오늘 하루도 {feeling} 하루였습니다.",
                "내일은 더 {hope} 하루가 되길 바랍니다.",
                "이렇게 저의 하루가 끝났습니다. {closing_phrase}",
            ]},
        ]
    },
    "취미": {
        "title_cn": "我的爱好",
        "categories": ["兴趣爱好", "日常问候"],
        "structure": [
            {"type": "opening", "cn": "开头", "templates": [
                "오늘은 제 취미에 대해 소개해 드리겠습니다.",
                "사람마다 다양한 취미가 있습니다. 저의 취미를 말씀드리겠습니다.",
                "저는 여러 가지 취미가 있습니다. 그중에서 가장 좋아하는 것을 소개하겠습니다.",
            ]},
            {"type": "body", "cn": "爱好介绍", "templates": [
                "제가 가장 좋아하는 취미는 {hobby}입니다.",
                "{hobby}은/는 제 인생에서 매우 중요한 부분입니다.",
                "저는 {frequency} {hobby}을/를 합니다. {reason}",
            ]},
            {"type": "body", "cn": "详细说明", "templates": [
                "{hobby}을/를 시작한 지 {duration} 되었습니다.",
                "{hobby}을/를 하면 {feeling} 기분이 듭니다.",
                "앞으로도 계속 {hobby}을/를 하면서 {goal}",
            ]},
            {"type": "closing", "cn": "结尾", "templates": [
                "여러분도 {hobby}에 도전해 보세요!",
                "취미는 우리 삶을 더 풍요롭게 만듭니다.",
                "이상으로 제 취미 소개를 마치겠습니다.",
            ]},
        ]
    },
    "여행": {
        "title_cn": "旅行计划",
        "categories": ["旅游观光", "交通出行", "购物消费", "饮食料理"],
        "structure": [
            {"type": "opening", "cn": "开头", "templates": [
                "이번 {season}에 {place}로 여행을 갈 계획입니다.",
                "저는 {place} 여행을 오랫동안 기다려 왔습니다.",
                "다음 주 {place}로 떠나는 여행에 대해 이야기해 보겠습니다.",
            ]},
            {"type": "body", "cn": "交通方式", "templates": [
                "{transport}을/를 타고 {place}에 갈 예정입니다.",
                "출발은 {departure}에서 하고, {transport}로 이동합니다.",
                "가는 길에 {sight}도 구경할 수 있어서 기대됩니다.",
            ]},
            {"type": "body", "cn": "计划活动", "templates": [
                "{place}에 도착하면 먼저 {activity1}을/를 할 겁니다.",
                "그리고 {food}도 꼭 먹어보고 싶습니다.",
                "마지막 날에는 {activity2}을/를 계획하고 있습니다.",
            ]},
            {"type": "closing", "cn": "结尾", "templates": [
                "이번 여행이 정말 기대됩니다!",
                "즐거운 여행이 될 것 같아요!",
                "여행 후에 또 후기를 남기겠습니다.",
            ]},
        ]
    },
    "음식": {
        "title_cn": "美食体验",
        "categories": ["饮食料理", "购物消费"],
        "structure": [
            {"type": "opening", "cn": "开头", "templates": [
                "오늘은 제가 가장 좋아하는 음식에 대해 이야기하겠습니다.",
                "한국에는 정말 맛있는 음식이 많습니다.",
                "요즘 제가 푹 빠진 음식을 소개해 드리겠습니다.",
            ]},
            {"type": "body", "cn": "食物描述", "templates": [
                "제가 가장 좋아하는 음식은 {food}입니다.",
                "{food}은/는 {taste} 맛이 나서 정말 맛있습니다.",
                "{food}을/를 먹으면 행복한 기분이 듭니다.",
            ]},
            {"type": "body", "cn": "制作过程", "templates": [
                "{food}을/를 만들 때는 {ingredient}이/가 필요합니다.",
                "만드는 방법은 {method} (으)로 하면 됩니다.",
                "저는 주로 {place}에서 {food}을/를 먹습니다.",
            ]},
            {"type": "closing", "cn": "结尾", "templates": [
                "여러분도 꼭 한번 드셔 보세요!",
                "정말 추천하는 음식이니 꼭 맛보세요!",
                "다음에는 다른 음식도 소개하겠습니다.",
            ]},
        ]
    },
    "학교_생활": {
        "title_cn": "校园生活",
        "categories": ["校园生活", "日常问候"],
        "structure": [
            {"type": "opening", "cn": "开头", "templates": [
                "오늘은 제 학교 생활에 대해 소개하겠습니다.",
                "저의 학교 생활은 {adjective} 매일매일입니다.",
                "학교에서 보내는 하루를 이야기해 보겠습니다.",
            ]},
            {"type": "body", "cn": "课程学习", "templates": [
                "저는 매일 아침 {time}시에 학교에 갑니다.",
                "제가 가장 좋아하는 과목은 {subject}입니다.",
                "수업 시간에 {activity}을/를 열심히 합니다.",
            ]},
            {"type": "body", "cn": "课余活动", "templates": [
                "쉬는 시간에는 친구들과 {activity}을/를 합니다.",
                "방과 후에는 {club} 동아리 활동에 참여합니다.",
                "학교 {place}에서 친구들과 재미있는 시간을 보냅니다.",
            ]},
            {"type": "closing", "cn": "结尾", "templates": [
                "학교 생활은 정말 즐겁고 의미 있습니다.",
                "앞으로도 열심히 공부하겠습니다!",
                "소중한 학교 생활을 즐기고 있습니다!",
            ]},
        ]
    },
}


@app.route("/api/themes", methods=["GET"])
def get_themes():
    """获取所有作文主题"""
    themes = []
    for key, val in ESSAY_THEMES.items():
        themes.append({
            "key": key,
            "title_cn": val["title_cn"],
            "categories": val["categories"]
        })
    return jsonify({"code": 0, "data": themes})


def pick_materials_by_categories(categories, count=4):
    """从指定分类中随机选取素材"""
    data = load_materials()
    pool = []
    for cat in categories:
        pool.extend([m for m in data["materials"] if m.get("category") == cat])
    if not pool:
        return []
    if len(pool) <= count:
        return pool
    return random.sample(pool, count)


def fill_template(template, materials, placeholders):
    """填充模板中的占位符"""
    result = template
    for key, val in placeholders.items():
        result = result.replace("{" + key + "}", val)
    return result


def smart_conjugate(korean_text):
    """简单的韩语助词选择 (은/는, 이/가, 을/를)"""
    if not korean_text:
        return korean_text
    result = korean_text
    patterns = [
        (r"\{(\w+)\}은/는", lambda m: f"{{{m.group(1)}}}은" if (ord(m.group(0)[-1]) - 0xAC00) % 28 != 0 else f"{{{m.group(1)}}}는"),
        (r"\{(\w+)\}이/가", lambda m: f"{{{m.group(1)}}}이" if (ord(m.group(0)[-1]) - 0xAC00) % 28 != 0 else f"{{{m.group(1)}}}가"),
        (r"\{(\w+)\}을/를", lambda m: f"{{{m.group(1)}}}을" if (ord(m.group(0)[-1]) - 0xAC00) % 28 != 0 else f"{{{m.group(1)}}}를"),
    ]
    for pattern, replacer in patterns:
        result = re.sub(pattern, replacer, result)
    return result


@app.route("/api/essay/generate", methods=["POST"])
def generate_essay():
    """生成固定主题作文（保留原功能）"""
    params = request.json
    theme_key = params.get("theme", "자기소개")
    essay_title = params.get("title", "")
    user_values = params.get("values", {})

    if theme_key not in ESSAY_THEMES:
        return jsonify({"code": 1, "msg": "未知主题"}), 400

    theme = ESSAY_THEMES[theme_key]
    materials_pool = pick_materials_by_categories(theme["categories"], count=6)

    default_placeholders = {
        "name": "철수",
        "age": "20",
        "hometown": "베이징",
        "hobby": "음악 감상",
        "hobby_detail": "주말마다 좋아하는 노래를 듣습니다.",
        "food": "김치찌개",
        "taste": "매콤하고 깊은",
        "ingredient": "김치와 돼지고기",
        "method": "끓이는 것",
        "place": "한국 식당",
        "time": "7",
        "transport": "버스",
        "activity": "공부",
        "activity1": "관광",
        "activity2": "쇼핑",
        "morning_activity": "수업",
        "afternoon_activity": "도서관에서 공부",
        "lunch_place": "학교 식당",
        "adjective": "즐거운",
        "feeling": "보람찬",
        "hope": "좋은",
        "closing_phrase": "내일도 힘내세요!",
        "frequency": "일주일에 두 번",
        "reason": "스트레스가 풀리기 때문입니다.",
        "duration": "3년",
        "goal": "더 실력을 키우고 싶습니다.",
        "season": "여름",
        "departure": "서울역",
        "sight": "아름다운 풍경",
        "subject": "한국어",
        "club": "음악",
    }
    placeholders = {**default_placeholders, **user_values}

    # 用素材覆盖占位符
    for m in materials_pool:
        cat = m.get("category", "")
        if cat == "饮食料理":
            placeholders["food"] = m.get("korean", placeholders["food"])
            placeholders["ingredient"] = m.get("example", placeholders["ingredient"])
        elif cat == "兴趣爱好":
            placeholders["hobby"] = m.get("korean", placeholders["hobby"])
            placeholders["hobby_detail"] = m.get("example", placeholders["hobby_detail"])
        elif cat == "交通出行":
            placeholders["transport"] = m.get("korean", placeholders["transport"])
        elif cat == "日常问候":
            placeholders["closing_phrase"] = m.get("korean", placeholders["closing_phrase"])

    paragraphs = []
    title = essay_title or theme["title_cn"]
    paragraphs.append(f"# {theme_key.replace('_', ' ')} ({title})\n")

    used_materials_summary = []

    for section in theme["structure"]:
        template = random.choice(section["templates"])
        processed_tpl = smart_conjugate(template)
        paragraph = fill_template(processed_tpl, materials_pool, placeholders)
        paragraphs.append(paragraph)

        if section["type"] == "body" and random.random() > 0.5 and materials_pool:
            extra_m = random.choice(materials_pool)
            if extra_m.get("example"):
                paragraphs.append(f"예를 들어, {extra_m['example']}")
                used_materials_summary.append({
                    "korean": extra_m["korean"],
                    "chinese": extra_m["chinese"],
                    "example": extra_m["example"],
                    "category": extra_m.get("category", "")
                })

        paragraphs.append("")

    essay = "\n".join(paragraphs)

    return jsonify({
        "code": 0,
        "data": {
            "title": title,
            "theme_key": theme_key,
            "essay": essay,
            "used_materials": used_materials_summary,
            "materials_count": len(materials_pool),
            "categories_used": theme["categories"]
        }
    })


# ==================== DeepSeek API 配置与调用 ====================
def call_deepseek_api(prompt, api_key, model="deepseek-chat"):
    """调用 DeepSeek API 生成作文 (兼容 openai>=1.0.0)"""
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位韩语写作老师，擅长生成自然、地道的韩语短文。请严格按照要求输出韩语，不要添加额外解释。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return None


# 简单的内存限流（每个 IP 每小时最多 10 次 AI 调用）
rate_limit_store = {}
def check_rate_limit(ip, limit=10, window=3600):
    now = time()
    if ip not in rate_limit_store:
        rate_limit_store[ip] = []
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < window]
    if len(rate_limit_store[ip]) >= limit:
        return False
    rate_limit_store[ip].append(now)
    return True


@app.route("/api/essay/custom", methods=["POST"])
def generate_custom_essay():
    """
    生成自定义主题作文（支持 AI 增强模式或本地规则模式）
    请求体：
    {
        "title": "我最爱的季节",
        "keywords": ["春天", "花", "温暖"],
        "use_ai": true,
        "api_key": "your-deepseek-key" (可选，如果没有则从环境变量读取)
    }
    """
    data = request.json
    title = data.get("title", "").strip()
    keywords = data.get("keywords", [])
    use_ai = data.get("use_ai", False)
    user_api_key = data.get("api_key", "")

    if not title:
        return jsonify({"code": 1, "msg": "请输入作文标题"}), 400

    # 获取当前用户素材（用于规则模式参考）
    materials_data = load_materials()
    all_materials = materials_data["materials"]
    sample_materials = random.sample(all_materials, min(10, len(all_materials))) if all_materials else []

    # 模式1：AI 增强模式
    if use_ai:
        # 获取 API key：优先使用用户传入的，其次环境变量
        api_key = user_api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            return jsonify({"code": 1, "msg": "AI 模式需要提供 DeepSeek API Key，请在设置中填写或使用本地模式"}), 400

        # 限流检查（获取客户端 IP）
        client_ip = request.remote_addr
        if not check_rate_limit(client_ip):
            return jsonify({"code": 1, "msg": "AI 调用次数过多，请稍后再试（每小时最多10次）"}), 429

        # 构建 prompt
        keywords_str = ", ".join(keywords) if keywords else "相关主题"
        prompt = f"""请用韩语写一篇题为“{title}”的短文，约200~300字。
主题关键词：{keywords_str}
要求：
- 使用韩语标准语（해요체 或 합니다체）
- 内容自然、流畅，包含开头、正文、结尾
- 尽可能使用初级到中级词汇
- 不要包含任何中文注释，只输出韩语正文
"""
        # 调用 API
        essay_korean = call_deepseek_api(prompt, api_key)
        if essay_korean is None:
            return jsonify({"code": 1, "msg": "AI 调用失败，请检查 API Key 或网络"}), 500

        # 估算消耗（粗略：每1000 token ~ 0.001元，提示用户）
        estimated_cost = 0.0015
        return jsonify({
            "code": 0,
            "data": {
                "title": title,
                "essay": essay_korean,
                "mode": "ai",
                "estimated_cost": estimated_cost,
                "note": "本次生成使用了 DeepSeek API"
            }
        })

    # 模式2：本地规则生成（免费，不消耗 token）
    else:
        # 使用增强的规则模板（基于预置场景和关键词匹配）
        matched_theme = None
        theme_keywords = {
            "자기소개": ["介绍", "자기소개", "我是", "名字"],
            "취미": ["爱好", "취미", "喜欢", "취미생활"],
            "여행": ["旅行", "여행", "旅游", "여행지"],
            "음식": ["美食", "음식", "吃", "맛있다"],
            "학교_생활": ["学校", "학교", "校园", "공부"],
            "나의_하루": ["一天", "하루", "日常", "일상"],
            "날씨": ["天气", "날씨", "季节", "계절"]
        }
        for theme_key, kw_list in theme_keywords.items():
            if any(kw in title for kw in kw_list):
                matched_theme = theme_key
                break
        if not matched_theme:
            matched_theme = "자기소개"  # 默认自我介绍主题

        theme = ESSAY_THEMES.get(matched_theme, ESSAY_THEMES["자기소개"])
        materials_pool = pick_materials_by_categories(theme["categories"], count=6)

        default_placeholders = {
            "name": "김철수",
            "age": "20",
            "hometown": "서울",
            "hobby": "음악 감상",
            "hobby_detail": "특히 발라드를 좋아해요",
            "food": "김치찌개",
            "taste": "매콤하고 구수한",
            "place": "한국",
            "time": "8",
            "transport": "지하철",
            "activity": "공부하기",
            "activity1": "관광지 방문",
            "activity2": "쇼핑",
            "morning_activity": "아침 운동",
            "afternoon_activity": "친구와 산책",
            "lunch_place": "학교 식당",
            "adjective": "즐거운",
            "feeling": "뿌듯한",
            "hope": "나은",
            "closing_phrase": "감사합니다!",
            "frequency": "매일",
            "reason": "마음이 편안해져서",
            "duration": "일 년",
            "goal": "더 발전하고 싶어요",
            "season": "가을",
            "departure": "서울역",
            "sight": "아름다운 경치",
            "subject": "한국어",
            "club": "독서 동아리",
        }
        # 从素材中提取一些真实词汇覆盖占位符
        for m in materials_pool:
            cat = m.get("category", "")
            if cat == "兴趣爱好" and "hobby" in default_placeholders:
                default_placeholders["hobby"] = m.get("korean", default_placeholders["hobby"])
            elif cat == "饮食料理" and "food" in default_placeholders:
                default_placeholders["food"] = m.get("korean", default_placeholders["food"])
            elif cat == "交通出行" and "transport" in default_placeholders:
                default_placeholders["transport"] = m.get("korean", default_placeholders["transport"])

        paragraphs = []
        paragraphs.append(f"# {title}\n")
        for section in theme["structure"]:
            template = random.choice(section["templates"])
            processed_tpl = smart_conjugate(template)
            paragraph = fill_template(processed_tpl, materials_pool, default_placeholders)
            paragraphs.append(paragraph)
            paragraphs.append("")
        essay = "\n".join(paragraphs)

        return jsonify({
            "code": 0,
            "data": {
                "title": title,
                "essay": essay,
                "mode": "local",
                "note": "本地规则生成，免费"
            }
        })


# ==================== 初始化示例数据 ====================
def init_sample_data():
    """如果没有数据则初始化示例数据"""
    data = load_materials()
    if data["materials"]:
        return

    samples = [
        {"korean": "안녕하세요", "chinese": "你好", "category": "日常问候", "difficulty": "初级",
         "example": "안녕하세요, 처음 뵙겠습니다.", "example_cn": "你好，初次见面。", "tags": ["问候", "正式"]},
        {"korean": "감사합니다", "chinese": "谢谢", "category": "日常问候", "difficulty": "初级",
         "example": "도와주셔서 정말 감사합니다.", "example_cn": "非常感谢您的帮助。", "tags": ["感谢", "礼貌"]},
        {"korean": "죄송합니다", "chinese": "对不起", "category": "日常问候", "difficulty": "初级",
         "example": "늦어서 죄송합니다.", "example_cn": "对不起，我迟到了。", "tags": ["道歉"]},
        {"korean": "반갑습니다", "chinese": "很高兴见到你", "category": "日常问候", "difficulty": "初级",
         "example": "만나서 반갑습니다.", "example_cn": "见到您很高兴。", "tags": ["问候"]},
        {"korean": "김치찌개", "chinese": "泡菜汤", "category": "饮食料理", "difficulty": "中级",
         "example": "김치찌개는 한국의 대표적인 음식입니다.", "example_cn": "泡菜汤是韩国的代表性食物。", "tags": ["韩食", "汤类"]},
        {"korean": "불고기", "chinese": "烤肉", "category": "饮食料理", "difficulty": "初级",
         "example": "불고기는 외국인들에게 인기가 많습니다.", "example_cn": "烤肉很受外国人欢迎。", "tags": ["韩食", "肉类"]},
        {"korean": "비빔밥", "chinese": "拌饭", "category": "饮食料理", "difficulty": "初级",
         "example": "비빔밥은 여러 가지 채소와 고추장을 넣어 비벼 먹는 음식입니다.", "example_cn": "拌饭是放入各种蔬菜和辣椒酱拌着吃的食物。", "tags": ["韩食", "主食"]},
        {"korean": "떡볶이", "chinese": "炒年糕", "category": "饮食料理", "difficulty": "初级",
         "example": "떡볶이는 한국의 대표적인 길거리 음식입니다.", "example_cn": "炒年糕是韩国代表性的街头小吃。", "tags": ["韩食", "小吃"]},
        {"korean": "버스", "chinese": "公交车", "category": "交通出行", "difficulty": "初级",
         "example": "학교까지 버스로 30분 걸립니다.", "example_cn": "坐公交车到学校需要30分钟。", "tags": ["公共交通"]},
        {"korean": "지하철", "chinese": "地铁", "category": "交通出行", "difficulty": "初级",
         "example": "지하철이 버스보다 더 빠릅니다.", "example_cn": "地铁比公交更快。", "tags": ["公共交通"]},
        {"korean": "택시", "chinese": "出租车", "category": "交通出行", "difficulty": "初级",
         "example": "늦을 때는 택시를 타고 갑니다.", "example_cn": "迟到的时候坐出租车去。", "tags": ["交通方式"]},
        {"korean": "얼마예요", "chinese": "多少钱", "category": "购物消费", "difficulty": "初级",
         "example": "이 옷은 얼마예요?", "example_cn": "这件衣服多少钱？", "tags": ["价格", "问句"]},
        {"korean": "깎아 주세요", "chinese": "请便宜点", "category": "购物消费", "difficulty": "初级",
         "example": "조금만 깎아 주세요.", "example_cn": "请便宜一点。", "tags": ["讲价"]},
        {"korean": "시험", "chinese": "考试", "category": "校园生活", "difficulty": "初级",
         "example": "다음 주에 중요한 시험이 있습니다.", "example_cn": "下周有重要的考试。", "tags": ["学习"]},
        {"korean": "도서관", "chinese": "图书馆", "category": "校园生活", "difficulty": "初级",
         "example": "시험 기간에는 도서관에 사람이 많습니다.", "example_cn": "考试期间图书馆人很多。", "tags": ["地点"]},
        {"korean": "날씨", "chinese": "天气", "category": "天气季节", "difficulty": "初级",
         "example": "오늘 날씨가 정말 좋습니다.", "example_cn": "今天天气真好。", "tags": ["天气"]},
        {"korean": "봄", "chinese": "春天", "category": "天气季节", "difficulty": "初级",
         "example": "봄에는 꽃이 핍니다.", "example_cn": "春天花会开。", "tags": ["季节"]},
        {"korean": "수영", "chinese": "游泳", "category": "兴趣爱好", "difficulty": "初级",
         "example": "여름에는 수영을 자주 합니다.", "example_cn": "夏天经常游泳。", "tags": ["运动"]},
        {"korean": "음악 감상", "chinese": "听音乐", "category": "兴趣爱好", "difficulty": "初级",
         "example": "저는 K-POP을 자주 듣습니다.", "example_cn": "我经常听K-POP。", "tags": ["音乐"]},
        {"korean": "여행", "chinese": "旅行", "category": "旅游观光", "difficulty": "初级",
         "example": "방학 때 제주도로 여행을 갈 거예요.", "example_cn": "放假时要去济州岛旅行。", "tags": ["旅行"]},
        {"korean": "사진을 찍다", "chinese": "拍照", "category": "旅游观光", "difficulty": "初级",
         "example": "예쁜 풍경을 사진으로 남겼어요.", "example_cn": "用照片记录下了美丽的风景。", "tags": ["摄影"]},
        {"korean": "가족", "chinese": "家人", "category": "家庭生活", "difficulty": "初级",
         "example": "우리 가족은 모두 4명입니다.", "example_cn": "我家共有4口人。", "tags": ["家庭"]},
        {"korean": "운동", "chinese": "运动", "category": "健康医疗", "difficulty": "初级",
         "example": "건강을 위해 매일 운동을 합니다.", "example_cn": "为了健康每天运动。", "tags": ["健康", "运动"]},
        {"korean": "사랑해요", "chinese": "我爱你", "category": "情感表达", "difficulty": "初级",
         "example": "엄마, 사랑해요!", "example_cn": "妈妈，我爱你！", "tags": ["感情", "表达"]},
        {"korean": "회의", "chinese": "会议", "category": "职场工作", "difficulty": "中级",
         "example": "오후 2시에 회의가 있습니다.", "example_cn": "下午2点有会议。", "tags": ["工作"]},
        {"korean": "여름", "chinese": "夏天", "category": "天气季节", "difficulty": "初级",
         "example": "한국의 여름은 덥고 습합니다.", "example_cn": "韩国的夏天又热又潮。", "tags": ["季节"]},
        {"korean": "한국어", "chinese": "韩语", "category": "校园生活", "difficulty": "初级",
         "example": "저는 한국어를 열심히 공부하고 있습니다.", "example_cn": "我正在努力学习韩语。", "tags": ["语言", "学习"]},
        {"korean": "친구", "chinese": "朋友", "category": "日常问候", "difficulty": "初级",
         "example": "한국 친구를 사귀고 싶습니다.", "example_cn": "想交韩国朋友。", "tags": ["社交"]},
    ]

    for i, s in enumerate(samples):
        s["id"] = i + 1
        s.setdefault("example", "")
        s.setdefault("example_cn", "")
        s.setdefault("tags", [])
        s.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    data["materials"] = samples
    data["next_id"] = len(samples) + 1
    save_materials(data)
    print(f"已初始化 {len(samples)} 条示例素材")


if __name__ == "__main__":
    init_sample_data()
    print("=" * 60)
    print("  韩语日常素材库积累与主题作文智能生成工具")
    print("  Korean Daily Material Corpus & Theme Essay Generator")
    print("=" * 60)
    port = int(os.environ.get("PORT", 8080))
    print(f"  访问地址: http://0.0.0.0:{port}")
    print(f"  数据目录: {DATA_DIR}")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=port)