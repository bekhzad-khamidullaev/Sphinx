from typing import List, Dict
from hrbot.models import Evaluation, Question

async def compute_avg_scores():
    """Compute average scores per question across all evaluations."""
    from asgiref.sync import sync_to_async
    evs = await sync_to_async(list)(Evaluation.objects.all())
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for ev in evs:
        for q, a in ev.responses.items():
            if a is not None and a.isdigit():
                sums[q] = sums.get(q, 0) + float(a)
                counts[q] = counts.get(q, 0) + 1
    return {q: sums[q] / counts[q] for q in sums}