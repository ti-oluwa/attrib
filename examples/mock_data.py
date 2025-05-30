#############
# MOCK DATA #
#############
year_data = [
    {
        "id": "1",  # should be int
        "name": "2019/2020",
        "start_date": "01-09-2019",  # changed to "d-m-Y"
        "end_date": "30-06-2020",  # changed to "d-m-Y"
    },
    {
        "id": 2,
        "name": 20202021,  # should be str
        "start_date": "2020-09-01",
        "end_date": "30/06/2021",  # changed to "d/m/Y"
    },
    {
        "id": "3",  # should be int
        "name": "2021/2022",
        "start_date": "2021/09/01",  # unusual format "Y/m/d"
        "end_date": "2022-06-30",
    },
    {
        "id": 4,
        "name": "2022/2023",
        "start_date": "September 1, 2022",  # non-standard format
        "end_date": "06-30-2023",  # changed to "m-d-Y",
    },
]


course_data = [
    {
        "id": "1",  # should be int
        "name": "Computer Science",
        "code": "CS101",
        "year": year_data[0],
    },
    {
        "id": 2,
        "name": "Mathematics",
        "code": 101,  # should be str
        "year": year_data[1],
    },
    {
        "id": 3,
        "name": "Physics",
        "code": "PHY101",
        "year": year_data[1],
    },
    {
        "id": 4,
        "name": "Chemistry",
        "code": "CHEM101",
        "year": year_data[2],
    },
    {
        "id": 5,
        "name": "Biology",
        "code": "BIO101",
        "year": year_data[2],
    },
    {
        "id": 6,
        "name": "History",
        "code": "HIST101",
        "year": year_data[3],
    },
    {
        "id": 7,
        "name": "Geography",
        "code": "GEO101",
        "year": year_data[3],
    },
    {
        "id": "8",  # should be int
        "name": "Economics",
        "code": "ECON101",
        "year": year_data[0],
    },
    {
        "id": 9,
        "name": "Literature",
        "code": "LIT101",
        "year": year_data[0],
    },
    {
        "id": 10,
        "name": "Philosophy",
        "code": "PHIL101",
        "year": year_data[0],
    },
    {
        "id": "11",  # should be int
        "name": "Psychology",
        "code": "PSYCH101",
        "year": year_data[1],
    },
    {
        "id": 12,
        "name": "Sociology",
        "code": "SOC101",
        "year": year_data[1],
    },
    {
        "id": 13,
        "name": "Anthropology",
        "code": "ANTH101",
        "year": year_data[2],
    },
    {
        "id": 14,
        "name": "Political Science",
        "code": "POL101",
        "year": year_data[3],
    },
]


student_data = [
    {
        "id": 1,
        "name": "John Doe",
        "age": "20",  # should be int
        "email": "john@doe.com",
        "phone": "+1234567890",
        "year": year_data[0],
        "courses": [course_data[0], course_data[1], course_data[2]],
        "joined_at": "01-09-2019",  # changed to "d-m-Y"
    },
    {
        "id": 2,
        "name": "Jane Doe",
        "age": 21,
        "email": None,  # should be str
        "phone": "+1234567890",
        "year": year_data[1],
        "courses": [course_data[3], course_data[4], course_data[5]],
        "joined_at": "09/01/2019",  # changed to "d/m/Y"
    },
    {
        "id": "3",  # should be int
        "name": "Alice Smith",
        "age": "22",  # should be int
        "email": "alice@smith.com",
        "phone": "+1234567890",  # should be str
        "year": year_data[3],
        "courses": [course_data[6], course_data[7], course_data[8]],
        "joined_at": "2019-09-01",
    },
]
