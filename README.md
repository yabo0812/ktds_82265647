# MS AI 개발역량강화 과제 (유동희)

## 프로젝트 개요
 > 1. 서비스 운영하면서 과거에 유사한 케이스로 작성해 놓은 내용, 과거에 언제 뭐때문에 배포했는지 기억안나는 내용들때문에 위키 검색을 해보아도 잘 찾을수가 없다.
 > 2. 리눅스서버 운영이나 PostgreSQL 운영 관련 내용은 늘 구글링 한다.
 
이런 어려움을 이번 챗봇 에이전트 생성을 통해 해소해 보고자 함.

## 작업 순서
- Concluence에서 위키 페이지를 pdf로 다운로드
   * 크롤링시도하였으나 로그인 세션 생성에서 실패.
   * 사이트 전체를 html로 다운로드 하였으나 불필요하고 반복적인 tag가 너무 많아서 실패.
   * 용량이 너무 커서 위키페이지의 카테고리별로 샘플링하여 pdf로 다운로드하기로 결정.
   * 하위 페이지를 포함하여 pdf로 생성하였더니 pdf 파일도 너무 커져서 페이지 단위로 pdf로 생성하기로 결정.
   * markdown 양식으로 정리하기 용이하게 pdf로 다운로드 완료.  

- Confluence 내용을 다운로드한 pdf를 파싱하여 markdown 파일 생성
   * PyMuPDF로 pdf 내용을 파싱한후, chatgpt로 markdown양식으로 정리한 파일 생성 (parse_pdf_dir.py)
   * pdf 파일이 큰경우 md로 생성하면서 자꾸 요약하고 생략해서 pdf 파일을 페이지 단위로 그룹핑해서 md 파일로 생성하도록 별도 스크립트 작성 (parse_pdf_pages.py)

- 생성된 markdown 파일을 Azure Storage에 저장
- Azure AI Search에서 demp-text-embedding-3-small 모델로 Chungking & Embedding 진행
- Azure AI Search와 Azure OpenAI를 이용하여 콘솔 프롬프트 질문에 대한 답변 생성하는 스크립트 작성히여 접속정보 환경설정 점검 및 데이터 확인 수행.
- Streamlit을 이용하여 웹 UI로 Q&A 챗봇 앱 스크립트 작성.
- Streamlit 앱을 Azure App Service로 배포. 
- https://user15-demoweb-a7drcgfyhabpevf8.eastus2-01.azurewebsites.net/ 접속하여 내용 확인.
