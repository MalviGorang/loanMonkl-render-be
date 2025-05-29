from typing import List, Dict

# Course lists by type
STEM_COURSES = [
    "Computer Science",
    "Data Science",
    "Electrical Engineering",
    "Mechanical Engineering",
    "Chemical Engineering",
    "Biotechnology",
    "Mathematics",
    "Physics",
    "Information Technology",
    "Robotics"
]

NON_STEM_COURSES = [
    "English Literature",
    "History",
    "Psychology",
    "Sociology",
    "Political Science",
    "Arts",
    "Design",
    "Journalism",
    "Languages",
    "Philosophy"
]

MANAGEMENT_COURSES = [
    "Master of Business Administration (MBA)",
    "Business Analytics",
    "Finance",
    "Marketing",
    "Human Resource Management",
    "International Business",
    "Supply Chain Management",
    "Operations Management",
    "Project Management",
    "Entrepreneurship"
]

def get_courses_by_type(course_type: str) -> List[str]:
    """
    Get list of courses based on course type.
    """
    course_map = {
        "STEM": STEM_COURSES,
        "Non-STEM": NON_STEM_COURSES,
        "Management": MANAGEMENT_COURSES
    }
    return course_map.get(course_type, [])
