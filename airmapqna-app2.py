import os
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime

# OpenAI 및 Azure 라이브러리 임포트
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# .env 파일에서 환경 변수 로드
load_dotenv()

# Azure OpenAI (RAG 및 임베딩용)
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBBEDING_MODEL_NAME = os.getenv("AZURE_OPENAI_EMBBEDING_MODEL_NAME")
AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME")
AZURE_OPENAI_EMBBEDING_API_VERSION = os.getenv("AZURE_OPENAI_EMBBEDING_API_VERSION")
AZURE_OPENAI_CHAT_MODEL_NAME = os.getenv("AZURE_OPENAI_CHAT_MODEL_NAME")
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

# Azure AI Search (RAG 검색용)
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_API_KEY")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME2")

# Streamlit 페이지 설정
st.set_page_config(
    page_title="에어맵 운영 Q&A",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 사용자 정의 CSS - 더 깔끔한 스타일
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 0.5rem;
        background: linear-gradient(90deg, #066CEA 0%, #18CBEB 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
            
    .main-header h1 {
        font-size: 2rem;
    }            
    
    [data-testid="stSidebar"] {
        background-color: #F3F3EE; 
    }
    
    /* 채팅 입력 영역 고정 */
    .stChatInput > div {
        position: sticky;
        bottom: 0;
        z-index: 1000;
    }
    
    /* 스크롤 최적화 */
    .element-container {
        max-height: none;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_clients():
    """
    Azure 및 OpenAI 클라이언트를 초기화하고 캐시합니다.
    """
    try:
        # 1. Azure OpenAI 클라이언트 (RAG용)
        azure_openai_client = AzureOpenAI(
            api_version=AZURE_OPENAI_EMBBEDING_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        
        # 2. Azure AI Search 클라이언트 (RAG 검색용)
        search_client = SearchClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX_NAME,
            credential=AzureKeyCredential(AZURE_SEARCH_KEY)
        )

        # 3. Azure OpenAI 클라이언트 (외부검색용)
        openai_client = AzureOpenAI(
            api_version=AZURE_OPENAI_EMBBEDING_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        
        return azure_openai_client, search_client, openai_client
    except (ValueError, TypeError, KeyError, Exception) as e:
        st.error(f"클라이언트 초기화 실패: {e}")
        return None, None, None

def route_question(query):
    """
    질문의 종류를 판단하여 처리 경로를 반환합니다.
    """
    query_lower = query.lower()

    if "리눅스" in query_lower or "linux" in query_lower:
        return "linux"
    elif "포스트그레" in query_lower or "포스트그레스" in query_lower or "postgres" in query_lower or "postgresql" in query_lower:
        return "postgres"
    else:
        return "wiki"

def get_rag_response(query, azure_openai_client, search_client):
    """
    Azure AI Search와 Azure OpenAI를 사용해 RAG 답변을 생성합니다.
    """
    try:
        # 1. 사용자 질문을 임베딩으로 변환 (벡터 검색용)
        embedding_response = azure_openai_client.embeddings.create(
            input=[query],
            model=AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME
        ).data[0].embedding
        
        vector_query = VectorizedQuery(vector=embedding_response, k_nearest_neighbors=3, fields="content_embedding")

        # 2. Azure AI Search에서 하이브리드 검색 (텍스트 + 벡터)
        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["document_title", "content_text"],
            top=10
        )

        # 3. 검색 결과를 컨텍스트로 구성
        formatted_results = []
        for result in results:            
            title = result.get("document_title", "제목 없음")
            content = result.get("content_text", "")
            score = result.get('@search.rerank_score', result.get('@search.score', 0.0))
            if content:
                formatted_results.append(
                    f"[문서 정보]\n"
                    f"제목: {title}\n"
                    f"관련성 점수: {score:.4f}\n\n"
                    f"[내용]\n{content}...\n"
                )
        context = "\n\n---\n\n".join(formatted_results)
        
        if not context:
            return "관련된 위키 정보를 찾을 수 없습니다."

        # 4. LLM에 전달할 프롬프트 구성
        system_message = """
        당신은 사내 위키 전문가 챗봇입니다.
        아래에 제공된 위키 문서 내용을 바탕으로 사용자의 질문에 대해 정확하고 상세하게 한국어로 답변해 주세요.
        문서에 없는 내용은 답변하지 말고, "정보를 찾을 수 없습니다"라고 답변하세요.
        """
        
        response = azure_openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"## 위키 문서:\n{context}\n\n## 질문:\n{query}"}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"죄송합니다, RAG 정보를 조회하는 데 문제가 발생했습니다.: {e}"

def get_external_response(query, topic, openai_client):
    """
    Azure OpenAI API를 사용해 특정 주제에 대한 일반 답변을 생성합니다.
    """
    topic_map = {
        "linux": "당신은 리눅스 명령어와 쉘 스크립트 전문가입니다.",
        "postgres": "당신은 PostgreSQL 데이터베이스 성능 튜닝 및 SQL 전문가입니다."
    }
    system_message = topic_map.get(topic, "당신은 유용한 AI 어시스턴트입니다.")
    system_message += " 사용자의 질문에 대해 전문가 수준의 정확한 정보를 한국어로 제공해 주세요. 필요한 경우 코드 예시를 포함해 주세요."
    system_message += " 당신의 전문분야 외의 정보는 전혀 모릅니다."

    try:
        response = openai_client.chat.completions.create(
            model=AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": query}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"죄송합니다, 정보를 조회하는 데 문제가 발생했습니다.: {e}"

def generate_response(query, clients):
    """응답 생성 함수"""
    aoai_client, search_client, openai_client = clients
    
    topic = route_question(query)
    
    if topic == "wiki":
        return get_rag_response(query, aoai_client, search_client)
    else:
        return get_external_response(query, topic, openai_client)

def main():
    # 헤더
    st.markdown("""
    <div class="main-header">
        <h1>에어맵 운영 Q&A</h1>
        <p>리눅스, PostgreSQL, 위키 정보를 검색할 수 있습니다</p>
    </div>
    """, unsafe_allow_html=True)

    # 사이드바
    with st.sidebar:
        st.header("☀️ 에어맵 운영 Q&A")
        st.info("에어맵 위키(Confluence) 내용 기반의 운영 이력을 검색하고, 리눅스 및 PostgreSQL 관련 운영시 필요한 검색에 활용합니다.")
        
        st.header("⚙️설정")
        if st.button("대화 기록 초기화"):
            st.session_state.messages = []
            st.rerun()
        
        st.header("🔎 사용 팁")
        st.write("✓&nbsp;&nbsp;리눅스 관련 질문시 'linux' 또는 '리눅스' 포함")
        st.write("✓&nbsp;&nbsp;PostgreSQL 관련 질문시 'postgres' 또는 'postgresql' 포함")
        st.write("✓&nbsp;&nbsp;그외 키워드에 대한 질문은 위키에서만 검색되고, 다른 정보 검색은 불가능합니다.")

    # 클라이언트 로드
    clients = load_clients()
    if not all(clients):
        st.error("클라이언트 초기화에 실패했습니다. 환경 변수를 확인해주세요.")
        return

    # 세션 상태 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 초기 메시지 추가 (첫 실행 시에만)
    if not st.session_state.messages:
        st.session_state.messages.append({
            "role": "assistant",
            "content": "안녕하세요! 에어맵 서비스 운영하면서 궁금한 것들을 물어보세요."
        })

    # 채팅 기록 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 사용자 입력 처리
    if prompt := st.chat_input("질문을 입력하세요..."):
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 어시스턴트 응답 생성 및 표시
        with st.chat_message("assistant"):
            with st.spinner("답변을 생성하고 있습니다..."):
                response = generate_response(prompt, clients)
                st.markdown(response)
        
        # 어시스턴트 메시지 저장
        st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()