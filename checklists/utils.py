from .models import Checklist, ChecklistResult, AnswerType, ChecklistItemStatus
import logging

logger = logging.getLogger(__name__)

def calculate_checklist_score(checklist_run: Checklist) -> float | None:
    """
    Calculates a score for a Checklist run based on its results.
    Scoring logic:
    - Only considers items with AnswerType SCALE_1_4, SCALE_1_5, NUMBER, YES_NO, YES_NO_MEH, BOOLEAN.
    - Items with status NOT_OK or PENDING are generally treated as non-contributing or negative.
    - Items with status NA are ignored for scoring.
    - Scale/Number: Use the numeric_value directly.
    - YES_NO: Yes=1, No=0.
    - YES_NO_MEH: Yes=1, Meh=0.5, No=0.
    - BOOLEAN: True=1, False=0.
    - A simple average is calculated from applicable and non-NOT_OK items.
    - Items with status NOT_OK reduce the score or are counted separately.
    - Let's implement a simple average of valid scores, potentially penalized by NOT_OK count.
    - Normalize score to a 0-100 percentage or keep the average value. Let's keep the average value for now.
    """
    results = checklist_run.results.filter(
        # Only consider results with statuses that imply an answer was given
        status__in=[ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK, ChecklistItemStatus.NOT_APPLICABLE]
    ).select_related('template_item') # Select related item for answer_type

    valid_scores = []
    item_count_for_average = 0 # Count items included in the average calculation
    not_ok_count = 0

    for result in results:
        item = result.template_item
        score_value = None # Score contributed by this item (normalized or raw)

        # Only process specific answer types for scoring
        if item.answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]:
            if result.numeric_value is not None:
                score_value = result.numeric_value
                item_count_for_average += 1
        elif item.answer_type == AnswerType.YES_NO:
             if result.value == 'yes':
                  score_value = 1.0
                  item_count_for_average += 1
             elif result.value == 'no':
                  score_value = 0.0
                  item_count_for_average += 1
        elif item.answer_type == AnswerType.YES_NO_MEH:
             if result.value == 'yes':
                  score_value = 1.0
                  item_count_for_average += 1
             elif result.value == 'yes_no_meh':
                  score_value = 0.5 # Intermediate score
                  item_count_for_average += 1
             elif result.value == 'no':
                  score_value = 0.0
                  item_count_for_average += 1
        elif item.answer_type == AnswerType.BOOLEAN:
            if result.boolean_value is True:
                 score_value = 1.0
                 item_count_for_average += 1
            elif result.boolean_value is False:
                 score_value = 0.0
                 item_count_for_average += 1

        # --- Scoring Logic based on Status ---
        if result.status == ChecklistItemStatus.OK:
             # Item contributes its score_value (if applicable type)
             if score_value is not None:
                  valid_scores.append(score_value)
             # If it's a text field marked OK, it doesn't add a numeric score but counts towards total items checked?
             # Let's only average types that have a clear numeric value interpretation.
             # item_count_for_average is incremented above only for relevant types.

        elif result.status == ChecklistItemStatus.NOT_OK:
             # This item signifies an issue. How it affects score depends on desired logic.
             # Option 1: Treat it as a 0 or minimum score for its type (if applicable).
             # Option 2: Simply count it as a deduction or separate metric.
             # Option 3: Ignore its value for averaging, but track the count of NOT_OK.
             # Let's use Option 3 for averaging, and just count NOT_OK items.
             not_ok_count += 1
             # Do NOT add score_value to valid_scores for NOT_OK items under this logic.

        elif result.status == ChecklistItemStatus.NOT_APPLICABLE:
             # Ignore N/A items completely for scoring and counts.
             pass
        elif result.status == ChecklistItemStatus.PENDING:
             # Ignore pending items, they should ideally not exist in completed/approved checklists
             pass


    # Calculate the average score based on items contributing a numeric score (status OK)
    # Or average over all items *except* N/A and Pending?
    # Let's average OK items that have a numeric interpretation.
    if not valid_scores:
        average_score = None # Cannot calculate if no applicable items are OK
    else:
        average_score = sum(valid_scores) / len(valid_scores)

    # Optional: Adjust the average score based on the number of NOT_OK items
    # Example: Deduct points per NOT_OK item? This is highly specific to scoring needs.
    # Let's just return the average of the OK items and the count of NOT_OK items.
    # The 'score' field on Checklist is a single decimal. Storing the average seems most general.

    # Round the score to 2 decimal places
    final_score = round(average_score, 2) if average_score is not None else None

    # Note: This simple scoring doesn't account for weighted items, sections, etc.
    # It also doesn't penalize 'NOT_OK' items directly in the *average*, just counts them.
    # For displaying, you might show the average score *and* the number of issues.

    # The Checklist model only has one `score` field. We'll store the calculated average here.
    # The count of issues can be derived via has_issues() or querying results.

    return final_score


# Consider adding other utility functions here:
# - Function to generate scheduled checklists based on frequency/next_due_date
# - Function to export checklist data (CSV/Excel)
# - Functions for permission checks beyond basic LoginRequiredMixin
# - Logging/Auditing helpers