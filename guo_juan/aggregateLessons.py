import json
from collections import defaultdict

# Load your JSON file
with open("all_lessons.json", "r", encoding="utf-8") as f:
    data = json.load(f)

groups = defaultdict(
    lambda: {
        "lesson_count": 0,
        "total_probs": 0,
        "total_minutes": 0,
        "total_difficulty": 0,
    }
)

for row in data["rows"]:
    type_name = (row.get("typeName") or "").strip()
    collection_name = (row.get("collectionName") or "").strip()
    lesson_name = (row.get("lessonName") or "").strip()

    key = (type_name, collection_name, lesson_name)

    groups[key]["lesson_count"] += 1

    # numPubProbs
    num_probs = row.get("numPubProbs") or 0
    groups[key]["total_probs"] += num_probs

    # lessonLength (minutes)
    lesson_length = row.get("lessonLength") or 0
    groups[key]["total_minutes"] += lesson_length

    # lessonDifficulty
    difficulty = row.get("lessonDifficulty") or 0
    groups[key]["total_difficulty"] += difficulty

# Header
print(
    "Type,Collection,Lesson,Lesson Count,Total Problems,Total Time (HH:MM),Total Minutes,Avg Difficulty"
)

for (type_name, collection_name, lesson_name), values in groups.items():
    total_minutes = values["total_minutes"]

    # Convert to HH:MM
    hours = total_minutes // 60
    minutes = total_minutes % 60
    time_str = f"{hours:02d}:{minutes:02d}"

    # Average difficulty
    if values["lesson_count"] > 0:
        avg_difficulty = values["total_difficulty"] / values["lesson_count"]
    else:
        avg_difficulty = 0

    avg_difficulty = round(avg_difficulty, 2)

    print(
        f"{type_name},{collection_name},{lesson_name},{values['lesson_count']},{values['total_probs']},{time_str},{total_minutes},{avg_difficulty}"
    )
