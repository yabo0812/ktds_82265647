import os
import streamlit as st
from dotenv import load_dotenv

# OpenAI 및 Azure 라이브러리 임포트
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 클라이언트 초기화 (Streamlit 캐시를 사용해 리소스 재사용) ---
@st.cache_resource
def load_clients():
    """
    Azure 및 OpenAI 클라이언트를 초기화하고 캐시합니다.
    """
    try:
        # 1. Azure OpenAI 클라이언트 (RAG용)
        azure_openai_client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
        
        # 2. Azure AI Sear클라이언트ch  (RAG 검색용)
        search_client = SearchClient(
            endpoint=os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT"),
            index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
            credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY")),
        )
        
        return azure_openai_client, search_client
    except ValueError as e:
        st.error(f"환경 변수 설정 오류: {e}")
        return None, None    
    except KeyError as e:
        st.error(f"환경 변수 '{e.args[0]}'를 찾을 수 없습니다. .env 파일을 확인해 주세요.")
        return None, None
    except Exception as e:
        st.error(f"클라이언트 초기화 중 오류 발생: {e}")
        return None, None

# --- 핵심 로직 함수들 ---
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
        embedding = azure_openai_client.embeddings.create(
            input=[query],
            model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
        ).data[0].embedding
        
        vector_query = VectorizedQuery(vector=embedding, k_nearest_neighbors=3, fields="content_vector")

        # 2. Azure AI Search에서 하이브리드 검색 (텍스트 + 벡터)
        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["content"], # 검색 결과에서 가져올 필드
            top=3
        )

        # 3. 검색 결과를 컨텍스트로 구성
        context = " ".join([result["content"] for result in results])
        
        if not context:
            return "관련된 위키 정보를 찾을 수 없습니다."

        # 4. LLM에 전달할 프롬프트 구성
        system_message = """
        당신은 사내 위키 전문가 챗봇입니다.
        아래에 제공된 위키 문서 내용을 바탕으로 사용자의 질문에 대해 정확하고 상세하게 한국어로 답변해 주세요.
        문서에 없는 내용은 답변하지 말고, "정보를 찾을 수 없습니다"라고 답변하세요.
        """
        
        response = azure_openai_client.chat.completions.create(
            model=os.environ("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"## 위키 문서:\n{context}\n\n## 질문:\n{query}"}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"RAG 답변 생성 중 오류 발생: {e}")
        return "죄송합니다, 답변을 생성하는 데 문제가 발생했습니다."

def get_external_response(query, topic, azure_openai_client):
    """
    Azure OpenAI API를 사용해 특정 주제에 대한 일반 답변을 생성합니다.
    """
    topic_map = {
        "linux": "당신은 리눅스 명령어와 쉘 스크립트 전문가입니다.",
        "postgres": "당신은 PostgreSQL 데이터베이스 성능 튜닝 및 SQL 전문가입니다."
    }
    system_message = topic_map.get(topic, "당신은 유용한 AI 어시스턴트입니다.")
    system_message += " 사용자의 질문에 대해 전문가 수준의 정확한 정보를 한국어로 제공해 주세요. 필요한 경우 코드 예시를 포함해 주세요."

    try:
        response = azure_openai_client.chat.completions.create(
            model=os.environ("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"), # Azure의 배포된 모델 사용
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": query}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Azure OpenAI API 호출 중 오류 발생: {e}")
        return "죄송합니다, 외부 정보를 조회하는 데 문제가 발생했습니다."

# --- Streamlit UI 구성 ---
st.set_page_config(page_title="에어맵 운영 Q&A")
st.title("에어맵 운영 Q&A")
st.caption("에어맵을 운영하면서 자주 묻는 질문에 대한 답변을 제공합니다. 리눅스명령어, PostgreSQL 운영, 에어맵 위키검색에 대해 질문해 보세요.")

# 클라이언트 로드
aoai_client, search_client = load_clients()

# 클라이언트 로드 실패 시 앱 중단
if not all([aoai_client, search_client]):
    st.stop()

# 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 내용 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 사용자 입력 처리
if prompt := st.chat_input("질문을 입력하세요 (예: 리눅스 명령어, PostgreSQL 운영, 에어맵 위키 검색 등)"):
    # 사용자 메시지 표시 및 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 어시스턴트 답변 처리
    with st.chat_message("assistant"):
        with st.spinner("답변을 생성하는 중입니다..."):
            # 질문 라우팅
            topic = route_question(prompt)
            
            # 경로에 따라 적절한 함수 호출
            if topic == "wiki":
                response = get_rag_response(prompt, aoai_client, search_client)
            else:
                response = get_external_response(prompt, topic, aoai_client)
            
            st.markdown(response)

    # 어시스턴트 메시지 저장
    st.session_state.messages.append({"role": "assistant", "content": response})

