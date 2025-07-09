import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# .env 파일에서 환경 변수를 로드합니다 (권장 방식)
load_dotenv()

# --- 1. 서비스 정보 설정 ---
# Azure OpenAI (RAG 및 임베딩용)
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT =os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_MODEL_NAME = os.getenv("AZURE_OPENAI_EMBBEDING_MODEL_NAME")
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_EMBBEDING_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_EMBBEDING_API_VERSION")

# Azure AI Search (RAG 검색용)
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_API_KEY") # 검색용 쿼리 키

# Azure 인덱스에 정의된 벡터 필드의 이름
# 인덱스 생성 시 설정한 이름으로 변경해야 합니다.
VECTOR_FIELD_NAME = "text_vector" 

# --- 2. 쿼리를 벡터로 변환하는 함수 ---
def generate_embedding(text: str, client: AzureOpenAI) -> list[float]:
    """주어진 텍스트를 OpenAI 임베딩 모델을 사용해 벡터로 변환합니다."""
    print("사용자 쿼리를 벡터로 변환 중...")
    response = client.embeddings.create(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT_NAME,  # 기본 임베딩 모델
        input=text
    )
    return response.data[0].embedding

# --- 3. 벡터 검색을 실행하는 메인 함수 ---
def run_vector_search(query_text: str):
    """사용자 쿼리로 벡터 검색을 수행하고 결과를 출력합니다."""
    
    try:
        # OpenAI 클라이언트 초기화
        openai_client = AzureOpenAI(
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        
        # Azure Search 클라이언트 초기화
        search_client = SearchClient(
            endpoint=AZURE_SEARCH_ENDPOINT,
            index_name=AZURE_SEARCH_INDEX_NAME,
            credential=AzureKeyCredential(AZURE_SEARCH_KEY)
        )
        
        # 1단계: 사용자 쿼리를 벡터로 변환
        query_vector = generate_embedding(query_text, openai_client)
        
        # 2단계: 벡터 검색 쿼리 객체 생성
        vector_query = VectorizedQuery(
            vector=query_vector, 
            k_nearest_neighbors=1, # 가장 유사한 상위 K개의 결과를 가져옵니다.
            fields=VECTOR_FIELD_NAME # 검색할 벡터 필드 지정
        )
        
        print(f"\n'{query_text}'에 대해 유사도 검색을 시작합니다...")

        # 3단계: 벡터 검색 실행
        results = search_client.search(
            search_text=None,  # 벡터 검색만 수행할 경우 None으로 설정
            vector_queries=[vector_query],
            select=["title", "chunk"] # 반환받고 싶은 필드 지정 (실제 필드명으로 수정)
        )

        # 4단계: 결과 출력
        print("\n검색 결과:")
        for result in results:
            print(f"  [유사도 점수: {result['@search.score']:.4f}]")
            print(f"  - 제목: {result.get('title')}")
            print(f"  - 내용: {result.get('chunk', '')[:200]}...") # 내용 일부 출력
            print("-" * 20)

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")


if __name__ == '__main__':
    user_query = "CMS 마지막 배포일자를 알려줘"
    run_vector_search(user_query)
