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
            # 현재 크게 두가지 경우 250604 15:17
            # 1. begin document으로 시작... 맨 마지막에 seciton 등장해서 자름. 그리고 end document 등장하여 없애야 하는 경우
            # 2. begin document으로 시작... 맨 마지막에 seciton 등장해서 자름. 그리고 section 안에 begin 다시 등장하여 이 begin의 end 마주함. 살려야 함. 
            if final_found is not None:
                # 어떻게 구분하는가? begin이 section 안에서 등장했는가, 바깥에서 등장했는가? 
                begin_found = stack[-1]    
                begin_found.start() # begin 시작 위치
                final_found.start() # 마지막 section 시작 위치

                if begin_found.start() < final_found.start():
                    # 현재 마주한 begin-end가 현재(마지막) section 보다 앞서서 시작 됨. e.g. end{document} 등...
                    section_partial = tex_doc[final_found.start():found.start()]    # end{document} 제외하여 자름
                    sections.append(section_partial)
                    return sections                    
                
                # else: # 그렇지 않으면 계속 살려야 함. 언제까지? 바로 위의 경우처럼 begin-end가 현재 마지막 section 보다 앞서서 실행되었을 경우까지 그냥 냅둠. 




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