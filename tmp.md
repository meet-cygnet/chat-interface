# SAST Workflow Diagram

```mermaid
%%{init: {'theme': 'dark'}}%%
graph TD
    CM_A{Counter Model A\nReceives:\n- Report A\n- Report B\n- Memory\n- CVE context}
    CM_B{Counter Model B\nReceives:\n- Report B\n- Report A\n- Memory\n- CVE context}
    
    REPORT_A[Report A]
    REPORT_B[Report B]
    
    REFINED_B[Refined Report B\n(by Model A)\nfalse positives removed\nevidence challenged\nseverity adjusted\nconfidence adjusted]
    REFINED_A[Refined Report A\n(by Model B)\nfalse positives removed\nevidence challenged\nseverity adjusted\nconfidence adjusted]
    
    FM_C{Final Fresh Model C GPT-5.4\nReceives ALL FOUR REPORTS:\n1. Report A\n2. Report B\n3. Refined Report B by A\n4. Refined Report A by B\n+ memory}
    
    REPORT_A --> CM_B
    REPORT_B --> CM_A
    CM_A --> REFINED_B
    CM_B --> REFINED_A
    REPORT_A --> FM_C
    REPORT_B --> FM_C
    REFINED_A --> FM_C
    REFINED_B --> FM_C
    
    classDef dashed fill:none,stroke:#fff,stroke-width:2px,stroke-dasharray: 5 5
    class CM_A,CM_B,FM_C dashed
```