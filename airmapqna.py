import os
from dotenv import load_dotenv

# OpenAI 및 Azure 라이브러리 임포트
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# .env 파일에서 환경 변수 로드
load_dotenv()
# Azure OpenAI (RAG 및 임베딩용)
AZURE_OPENAI_API_KEY=os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT=os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_EMBBEDING_MODEL_NAME=os.getenv("AZURE_OPENAI_EMBBEDING_MODEL_NAME")
AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME=os.getenv("AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME")
AZURE_OPENAI_EMBBEDING_API_VERSION=os.getenv("AZURE_OPENAI_EMBBEDING_API_VERSION")
AZURE_OPENAI_CHAT_MODEL_NAME=os.getenv("AZURE_OPENAI_CHAT_MODEL_NAME")
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
AZURE_OPENAI_CHAT_API_VERSION=os.getenv("AZURE_OPENAI_CHAT_API_VERSION")

# Azure AI Search (RAG 검색용)
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_API_KEY") # 검색용 쿼리 키
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME")

def load_clients():
    """
    Azure 및 OpenAI 클라이언트를 초기화하고 캐시합니다.
    """
    try:
        # 1. Azure OpenAI 클라이언트 (RAG용)
        azure_openai_client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version=AZURE_OPENAI_EMBBEDING_API_VERSION,
        )
        
        # 2. Azure AI Sear클라이언트ch  (RAG 검색용)
        search_client = SearchClient(
            credential=AzureKeyCredential(AZURE_SEARCH_KEY),
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX_NAME,
        )

        # 3. Azure OpenAI 클라이언트 (외부검색용)
        openai_client = AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version=AZURE_OPENAI_CHAT_API_VERSION,
        )
        
        return azure_openai_client, search_client, openai_client
    except (ValueError, TypeError, KeyError, Exception) as e:
        print(f"클라이언트 초기화 실패: {e}")
        return None, None, None

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
        embeddingresponse  = azure_openai_client.embeddings.create(
            input=[query],
            model=AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME
        ).data[0].embedding
        
        vector_query = VectorizedQuery(vector=embeddingresponse, k_nearest_neighbors=3, fields="text_vector")

        # 2. Azure AI Search에서 하이브리드 검색 (텍스트 + 벡터)
        results = search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=["title", "chunk"], # 반환받고 싶은 필드 지정 (실제 필드명으로 수정)
            top=10 # 검색 결과의 상위 10개 문서만 가져오기
        )

        # 3. 검색 결과를 컨텍스트로 구성
        formatted_results = []
        for result in results:            
            title = result.get("title", "제목 없음")
            chunk = result.get("chunk", "")
            score = result.get('@search.rerv_score', result.get('@search.score', 0.0))
            if chunk:
                formatted_results.append(
                    f"[문서 정보]\n"
                    f"제목: {title}\n"
                    f"관련성 점수: {score:.4f}\n\n"
                    f"[내용]\n{chunk}...\n"
                )
        context = "\n\n---\n\n".join(formatted_results)
        
        if not context:
            return "관련된 위키 정보를 찾을 수 없습니다."

        # 4. LLM에 전달할 프롬프트 구성hi
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
            model=AZURE_OPENAI_CHAT_DEPLOYMENT_NAME, # Azure의 배포된 모델 사용
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": query}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"죄송합니다, 정보를 조회하는 데 문제가 발생했습니다.: {e}"

def main():
    """콘솔에서 챗봇을 실행하는 메인 함수입니다."""
    aoai_client, search_client, openchat_client = load_clients()
    if not all([aoai_client, search_client]):
        return # 클라이언트 로드 실패 시 종료
    
    print("=" * 40)
    print("  통합 정보 검색 콘솔 챗봇")
    print("  (종료하려면 'exit' 또는 '종료'를 입력하세요)")
    print("=" * 40)

    while True:
        try:
            # 사용자 입력 받기
            query = input("질문을 입력하세요: ").strip()
            if query.lower() in ["exit", "종료"]:
                print("챗봇을 종료합니다. 감사합니다!")
                break

            topic = route_question(query)
            if topic == "wiki":
                response = get_rag_response(query, aoai_client, search_client)
            else:
                response = get_external_response(query, topic, openchat_client)

            print(f"답변: {response}\n")
        except (KeyboardInterrupt, EOFError):
            print("\n챗봇을 종료합니다. 감사합니다!")
            break
        

if __name__ == "__main__":
    main()