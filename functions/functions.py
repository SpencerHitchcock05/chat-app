import random
import string

def gen_code():
    code = ""
    for _ in range(10):
        code += random.choice(string.ascii_letters)
    return code

def compare_group_dates(group):
    return group["last_message_time"]