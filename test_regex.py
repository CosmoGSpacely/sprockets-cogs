import re

text = '''I had appointments on March 15 at 9:30am and April 5 at 2:15pm.
I have upcoming appointments on September 10 at 10am and November 20 at 3:45pm.'''

# Patterns from extractor
numeric_pattern = r'(\d{1,2})/(\d{1,2})/(\d{2,4})'
named_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?'
time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)'

# Find all dates with their positions
numeric_matches = [(m.group(1), m.group(2), m.group(3), m.start()) for m in re.finditer(numeric_pattern, text)]
named_matches = [(m.group(1), m.group(2), m.start()) for m in re.finditer(named_pattern, text, re.IGNORECASE)]
time_matches = [(m.group(1), m.group(2) or '', m.group(3), m.start()) for m in re.finditer(time_pattern, text)]

print("Numeric matches:", numeric_matches)
print("\nNamed matches:", named_matches)
print("\nTime matches:", time_matches)

# Test find_nearest_time
def find_nearest_time(date_pos):
    if not time_matches:
        return None
    times_after = [t for t in time_matches if t[3] > date_pos]
    if times_after:
        hour, minute, ampm, _ = times_after[0]
        minute = minute if minute else '00'
        return f"{hour}:{minute} {ampm}"
    times_before = [t for t in time_matches if t[3] <= date_pos]
    if times_before:
        hour, minute, ampm, _ = times_before[-1]
        minute = minute if minute else '00'
        return f"{hour}:{minute} {ampm}"
    return None

print("\n\nFinding times for each date:")
for month, day, pos in named_matches:
    time = find_nearest_time(pos)
    print(f"  {month} {day} (pos {pos}) -> time: {time}")
