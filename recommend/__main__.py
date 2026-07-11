"""Demo entrypoint:  python3 -m recommend "build a lead-classification agent"
Runs seed if the collection is empty, then prints ranked recommendations.
"""
import sys

from db.client import get_vector_collection
from db.seed import seed
from recommend.engine import recommend


def main() -> None:
    task = " ".join(sys.argv[1:]) or "build a lead-classification agent for sales"
    if get_vector_collection().count() == 0:
        seed()
    results = recommend(task)
    print(f"\nTask: {task}\n")
    if not results:
        print("(no related assets found)")
        return
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['score']:.3f}] {r['title']}  — {r['owner_name']}")
        print(f"     problem: {r['problem']}")
        print(f"     used {r['usage_count']}x  (id={r['asset_id']})")


if __name__ == "__main__":
    main()
