from courses_data import COURSES, GRADE_ORDER


def parse_alternative(subject_str):
    """Parse a subject string that may contain alternatives separated by '/'.
    Returns a list of acceptable subjects.
    """
    return [s.strip() for s in subject_str.split("/")]


def check_subject_match(required_subjects, user_subjects):
    """Check if user's subjects satisfy all required subjects (with alternatives).
    
    Args:
        required_subjects: List of required subject strings (may contain "Subject1/Subject2")
        user_subjects: List of user's subjects (lowercase for comparison)
    
    Returns:
        (bool, list): (whether all required subjects are matched, list of matched items)
    """
    user_set = {s.lower().strip() for s in user_subjects}

    for req in required_subjects:
        alternatives = [a.lower().strip() for a in parse_alternative(req)]
        if not any(alt in user_set for alt in alternatives):
            return False
    return True


def get_missing_subjects(required_subjects, user_subjects):
    """Return which required subjects are missing from user's subjects.
    For alternatives, returns the whole group as missing if none match.
    """
    user_set = {s.lower().strip() for s in user_subjects}
    missing = []

    for req in required_subjects:
        alternatives = [a.lower().strip() for a in parse_alternative(req)]
        if not any(alt in user_set for alt in alternatives):
            missing.append(req)

    return missing


def check_sittings(sittings_count):
    """Check if number of sittings is acceptable (max 2)."""
    return sittings_count <= 2


def check_jamb_score(user_score, cut_off):
    """Check if user's JAMB score meets or exceeds cut-off."""
    return user_score >= cut_off


def check_requirement_dict(req, user_set):
    """Check if user_set satisfies a requirements dict with fixed/choices/any structure.

    Args:
        req: dict with keys 'fixed' (list), 'choices' (list of {from, count}), 'any' (int, optional)
        user_set: set of user's subjects (lowercase)

    Returns:
        bool: whether requirements are met
    """
    for subj in req.get("fixed", []):
        if subj.lower().strip() not in user_set:
            return False

    for group in req.get("choices", []):
        allowed = {s.lower().strip() for s in group["from"]}
        if len(user_set & allowed) < group["count"]:
            return False

    min_needed = len(req.get("fixed", []))
    for group in req.get("choices", []):
        min_needed += group["count"]
    min_needed += req.get("any", 0)

    return len(user_set) >= min_needed


def matches_jamb_subjects(course, user_jamb_subjects):
    """Check if user's JAMB subjects satisfy course JAMB requirements."""
    user_set = {s.lower().strip() for s in user_jamb_subjects}
    return check_requirement_dict(course["jamb_subjects"], user_set)


def matches_olevel(course, user_olevel_subjects):
    """Check if user's O'Level subjects satisfy course O'Level requirements.

    user_olevel_subjects: dict of {subject: grade} where grade is like "A1", "B2", etc.
    Only credits (C6 and above) count as passes.
    """
    credit_subjects = []
    for subject, grade in user_olevel_subjects.items():
        grade_code = grade.upper().strip()
        if grade_code in GRADE_ORDER and GRADE_ORDER[grade_code] <= 6:
            credit_subjects.append(subject)

    user_set = {s.lower().strip() for s in credit_subjects}
    return check_requirement_dict(course["olevel_subjects"], user_set)


def get_missing_olevel(course, user_olevel_subjects):
    """Return list of O'Level requirements missing from user's credits."""
    credit_subjects = []
    for subject, grade in user_olevel_subjects.items():
        grade_code = grade.upper().strip()
        if grade_code in GRADE_ORDER and GRADE_ORDER[grade_code] <= 6:
            credit_subjects.append(subject)
    user_set = {s.lower().strip() for s in credit_subjects}
    req = course["olevel_subjects"]
    missing = []

    for subj in req.get("fixed", []):
        if subj.lower().strip() not in user_set:
            missing.append(f"Fixed: {subj}")

    for group in req.get("choices", []):
        allowed = {s.lower().strip() for s in group["from"]}
        matched = len(user_set & allowed)
        if matched < group["count"]:
            missing.append(f"Need {group['count']} from: {', '.join(group['from'])}")

    any_count = req.get("any", 0)
    if any_count > 0:
        min_needed = len(req.get("fixed", []))
        for group in req.get("choices", []):
            min_needed += group["count"]
        min_needed += any_count
        if len(user_set) < min_needed:
            missing.append(f"Need {min_needed - len(user_set)} more credit(s)")

    return missing


def check_all_courses(user_score, user_jamb_subjects, user_olevel_subjects, sittings):
    """Main function: check user against all courses in the database.
    
    Args:
        user_score: int, JAMB score (0-400)
        user_jamb_subjects: list of 4 subject strings (including English)
        user_olevel_subjects: dict of {subject: grade}
        sittings: int, number of O'Level sittings (1 or 2)
    
    Returns:
        dict with keys:
            - "qualified": list of courses user qualifies for (fully)
            - "jamb_only": list of courses matching JAMB but not O'Level
            - "score_low": list of courses matching subjects but score too low
            - "wrong_jamb": list of courses where JAMB subjects don't match
            - "sittings_issue": bool, whether sittings exceed 2
    """
    result = {
        "qualified": [],
        "jamb_only": [],
        "score_low": [],
        "wrong_jamb": [],
        "sittings_issue": not check_sittings(sittings),
    }

    for course in COURSES:
        jamb_match = matches_jamb_subjects(course, user_jamb_subjects)
        score_match = check_jamb_score(user_score, course["cut_off"])
        olevel_match = matches_olevel(course, user_olevel_subjects)

        if jamb_match and score_match and olevel_match:
            result["qualified"].append(course)
        elif jamb_match and olevel_match and not score_match:
            result["score_low"].append(course)
        elif jamb_match and score_match and not olevel_match:
            missing = get_missing_olevel(course, user_olevel_subjects)
            result["jamb_only"].append({
                "course": course,
                "missing_subjects": missing,
            })
        elif not jamb_match:
            result["wrong_jamb"].append(course)

    return result
