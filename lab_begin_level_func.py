import re
def begin_end_searach(tex_doc):
    """
    - begin을 만나면 stack 시작
    - end을 만나면 pop
    - 현재 level 파악

    - section 만나면 다음 section의 시작을 파악하여 현재 section 구분해냄.
    - 다음 section이 존재하지 않으면 마지막 section이라고 판별
    - 마지막 section에서 (nested) begin end 구문 안에 들어가 있으면 end 구분 제거해냄.
    
    """
    stack = []
    final_found = None
    sections = []
    for found in re.finditer(r"\\begin{.+?}|\\end{.+?}|\\section{", tex_doc):
        if "begin" in found.group():
            stack.append(found)
        elif "end" in found.group():

            # 마지막 section에서 end 제거
            if final_found is not None:
                section_partial = tex_doc[final_found.start():found.start()]
                sections.append(section_partial)
                return sections

            stack.pop()
        else:
            # print(f"section found in begin end depth {len(stack)}")
            found_next = list(re.finditer(r"\\section{", tex_doc[found.end():]))
            if found_next:
                section_partial = tex_doc[found.start():len(tex_doc[:found.end()]) + found_next[0].start():]
                sections.append(section_partial)
            else: # 마지막 section. 다음 \\section을 찾을 수 없다. 
                # found: 마지막 section이 포함되어 있다. 그리고 begin end가 끝나지 않고 있을 수 있다. 
                final_found = found
    return sections