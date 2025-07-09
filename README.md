# MS AI 개발역량강화 과제 제출 (유동희)

## 작업 개요
- Confluence 내용을 다운로드한 pdf를 파싱하여 markdown 파일 생성
   - PyMuPDF 로 pdf 내용을 파싱한후, chatgpt로 markdown양식으로 정리한 파일 생성 (parse_pdf_dir.py)
   - pdf 파일이 큰경우 md로 생성하면서 자꾸 요약하고 생략해서 pdf 파일을 페이지 단위로 그룹핑해서 md 파일로 생성하도록 별도 스크립트 작성 (parse_pdf_pages.py)
- 생성된 markdown 파일을 Azure Storage에 저장
- Azure AI Search에서 Chungking & Embedding 진행
- Azure OpenAI를 이용하여 콘솔 프롬프트 질문에 대한 답변 생성하는 스크립트 작성(airmapqna.py
- Streamlit을 이용하여 웹 UI로 질문에 대한 답변 생성하는 앱 작성 (airmapqna_app.py)

