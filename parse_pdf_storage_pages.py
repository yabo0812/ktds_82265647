import os
import time
from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import AzureOpenAI
import json
import hashlib
from PIL import Image
import io
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

# 환경변수 
load_dotenv()

# Azure OpenAI 설정
azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") # Azure OpenAI 엔드포인트
azure_api_version = os.getenv("AZURE_OPENAI_CHAT_API_VERSION")  # Azure OpenAI API 버전
azure_deployment_name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")   # Azure OpenAI 배포된 모델 이름

# Azure Storage 설정
storage_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
storage_container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "documents")  # 기본값 설정

# OpenAI 클라이언트 초기화
client = AzureOpenAI(
    api_version=azure_api_version,
    azure_endpoint=azure_endpoint,
    api_key=azure_api_key
)

# Azure Storage 클라이언트 초기화
blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
container_client = blob_service_client.get_container_client(storage_container_name)

def download_blob_to_memory(blob_name):
    """Azure Storage에서 blob을 메모리로 다운로드"""
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_data = blob_client.download_blob().readall()
        return blob_data
    except AzureError as e:
        print(f"Blob 다운로드 오류 ({blob_name}): {e}")
        return None

def upload_blob_from_memory(blob_name, data, content_type="application/octet-stream"):
    """메모리의 데이터를 Azure Storage에 업로드"""
    try:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(data, overwrite=True, content_type=content_type)
        return f"https://{blob_service_client.account_name}.blob.core.windows.net/{storage_container_name}/{blob_name}"
    except AzureError as e:
        print(f"Blob 업로드 오류 ({blob_name}): {e}")
        return None

def extract_images_from_pdf_blob(pdf_blob_data, pdf_name):
    """PDF blob에서 이미지를 추출하고 Azure Storage에 저장"""
    # PDF 데이터를 메모리에서 열기
    doc = fitz.open(stream=pdf_blob_data, filetype="pdf")
    image_info = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            try:
                # 이미지 데이터 추출
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # 이미지 해시 생성 (중복 방지)
                img_hash = hashlib.md5(image_bytes).hexdigest()
                
                # 이미지 파일명 생성
                img_filename = f"{pdf_name}_page{page_num + 1}_img{img_index + 1}_{img_hash}.{image_ext}"
                img_blob_path = f"images/{img_filename}"
                
                # Azure Storage에 이미지 업로드
                content_type = f"image/{image_ext}"
                img_url = upload_blob_from_memory(img_blob_path, image_bytes, content_type)
                
                if img_url:
                    # 이미지 정보 저장
                    image_info.append({
                        "page_num": page_num + 1,
                        "img_index": img_index + 1,
                        "filename": img_filename,
                        "blob_path": img_blob_path,
                        "url": img_url,
                        "hash": img_hash
                    })
                    
                    print(f"이미지 업로드 완료: {img_blob_path}")
                
            except Exception as e:
                print(f"이미지 추출 오류 (페이지 {page_num + 1}, 이미지 {img_index + 1}): {e}")
    
    doc.close()
    return image_info

def extract_pdf_text_with_pages_blob(pdf_blob_data):
    """PDF blob에서 페이지별로 텍스트 추출"""
    doc = fitz.open(stream=pdf_blob_data, filetype="pdf")
    pages_text = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text = page.get_text()
        pages_text.append({
            "page_num": page_num + 1,
            "text": page_text
        })
    
    doc.close()
    return pages_text

def create_page_chunks(pages_text, chunk_size=40):
    """페이지들을 지정된 크기로 청크 분할"""
    chunks = []
    total_pages = len(pages_text)
    
    for i in range(0, total_pages, chunk_size):
        chunk_pages = pages_text[i:i + chunk_size]
        start_page = chunk_pages[0]["page_num"]
        end_page = chunk_pages[-1]["page_num"]
        
        # 청크 텍스트 결합
        chunk_text = ""
        for page_data in chunk_pages:
            chunk_text += f"\n\n--- 페이지 {page_data['page_num']} ---\n"
            chunk_text += page_data["text"]
        
        chunks.append({
            "start_page": start_page,
            "end_page": end_page,
            "text": chunk_text,
            "chunk_index": len(chunks)
        })
    
    return chunks

def get_images_for_chunk(image_info, start_page, end_page):
    """특정 페이지 범위에 해당하는 이미지 정보 반환"""
    chunk_images = []
    for img in image_info:
        if start_page <= img["page_num"] <= end_page:
            chunk_images.append(img)
    return chunk_images

def summarize_to_markdown(text, chunk_info, chunk_images):
    """텍스트를 마크다운으로 변환 (내용 생략 방지 강화)"""
    try:
        # 이미지 정보 텍스트 생성
        images_text = ""
        if chunk_images:
            images_text = "\n\n## 이미지 정보\n"
            for img in chunk_images:
                images_text += f"- 페이지 {img['page_num']}: {img['filename']} (URL: {img['url']})\n"
        
        prompt = f"""다음은 PDF에서 추출한 인터페이스 정의서 내용입니다 (페이지 {chunk_info['start_page']}-{chunk_info['end_page']}). 
이 내용을 Markdown 형식으로 변환해주세요. 

**중요 지침:**
1. 절대로 어떤 내용도 생략하거나 요약하지 마세요. 모든 내용을 그대로 포함해야 합니다.
2. 테이블, 코드, 예시, 상세 설명 등 모든 정보를 완전히 보존해주세요.
3. API 정보가 있다면 Request와 Response 샘플 JSON도 모두 포함해주세요.
4. 페이지 번호와 구조를 명확히 표시해주세요.
5. 원본 텍스트의 모든 세부사항을 유지해주세요.

{images_text}

원본 내용:
{text}"""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            model=azure_deployment_name,
            max_tokens=4000
        )
        return response.choices[0].message.content
    except openai.error.RateLimitError as e:
        print(f"요청이 너무 많습니다. 잠시 후 다시 시도해주세요. 오류: {e}")
        time.sleep(60)
        return summarize_to_markdown(text, chunk_info, chunk_images)
    except Exception as e:
        print(f"마크다운 변환 오류: {e}")
        return None

def create_metadata_blob(pdf_name, chunks_info, image_info):
    """메타데이터를 Azure Storage에 저장"""
    metadata = {
        "pdf_name": pdf_name,
        "total_chunks": len(chunks_info),
        "chunks": chunks_info,
        "images": image_info,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    metadata_blob_path = f"{pdf_name}_metadata.json"
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    
    metadata_url = upload_blob_from_memory(
        metadata_blob_path, 
        metadata_json.encode('utf-8'), 
        "application/json"
    )
    
    return metadata_url, metadata_blob_path

def list_pdf_blobs():
    """Azure Storage에서 PDF 파일 목록 조회"""
    try:
        pdf_blobs = []
        blobs = container_client.list_blobs()
        for blob in blobs:
            if blob.name.lower().endswith('.pdf'):
                pdf_blobs.append(blob.name)
        return pdf_blobs
    except AzureError as e:
        print(f"Blob 목록 조회 오류: {e}")
        return []

def process_pdf_blob(pdf_blob_name):
    """단일 PDF blob 처리"""
    pdf_name = os.path.splitext(os.path.basename(pdf_blob_name))[0]
    print(f"처리 중: {pdf_blob_name}")
    
    # 1. PDF blob 다운로드
    print("PDF 다운로드 중...")
    pdf_data = download_blob_to_memory(pdf_blob_name)
    if not pdf_data:
        print(f"PDF 다운로드 실패: {pdf_blob_name}")
        return False
    
    # 2. 이미지 추출 및 업로드
    print("이미지 추출 및 업로드 중...")
    image_info = extract_images_from_pdf_blob(pdf_data, pdf_name)
    print(f"추출된 이미지 수: {len(image_info)}")
    
    # 3. 페이지별 텍스트 추출
    print("텍스트 추출 중...")
    pages_text = extract_pdf_text_with_pages_blob(pdf_data)
    total_pages = len(pages_text)
    print(f"총 페이지 수: {total_pages}")
    
    # 4. 페이지 청크 분할
    chunks = create_page_chunks(pages_text, chunk_size=40)
    print(f"생성된 청크 수: {len(chunks)}")
    
    # 5. 각 청크를 마크다운으로 변환 및 업로드
    chunks_info = []
    for chunk in chunks:
        chunk_images = get_images_for_chunk(image_info, chunk["start_page"], chunk["end_page"])
        
        print(f"청크 {chunk['chunk_index'] + 1} 변환 중 (페이지 {chunk['start_page']}-{chunk['end_page']})")
        markdown_text = summarize_to_markdown(chunk["text"], chunk, chunk_images)
        
        if markdown_text:
            # 청크별 마크다운 파일 Azure Storage에 업로드
            if len(chunks) == 1:
                md_filename = f"{pdf_name}.md"
            else:
                md_filename = f"{pdf_name}_part{chunk['chunk_index'] + 1}_pages{chunk['start_page']}-{chunk['end_page']}.md"
            
            md_blob_path = f"{md_filename}"
            md_url = upload_blob_from_memory(
                md_blob_path, 
                markdown_text.encode('utf-8'), 
                "text/markdown"
            )
            
            if md_url:
                chunks_info.append({
                    "chunk_index": chunk['chunk_index'],
                    "start_page": chunk['start_page'],
                    "end_page": chunk['end_page'],
                    "filename": md_filename,
                    "blob_path": md_blob_path,
                    "url": md_url,
                    "images": chunk_images
                })
                
                print(f"마크다운 업로드 완료: {md_blob_path}")
            else:
                print(f"마크다운 업로드 실패: {md_filename}")
            
            # API 호출 간격 조절
            time.sleep(2)
        else:
            print(f"청크 {chunk['chunk_index'] + 1} 변환 실패")
    
    # 6. 메타데이터 업로드
    metadata_url, metadata_blob_path = create_metadata_blob(pdf_name, chunks_info, image_info)
    if metadata_url:
        print(f"메타데이터 업로드 완료: {metadata_blob_path}")
    else:
        print("메타데이터 업로드 실패")
    
    print(f"'{pdf_blob_name}' 처리 완료!\n")
    return True

def process_all_pdf_blobs():
    """Azure Storage의 모든 PDF 파일 처리"""
    pdf_blobs = list_pdf_blobs()
    
    if not pdf_blobs:
        print("처리할 PDF 파일이 없습니다.")
        return
    
    print(f"발견된 PDF 파일: {len(pdf_blobs)}개")
    for pdf_blob in pdf_blobs:
        print(f"- {pdf_blob}")
    
    print("\n처리를 시작합니다...\n")
    
    success_count = 0
    for pdf_blob in pdf_blobs:
        if process_pdf_blob(pdf_blob):
            success_count += 1
    
    print(f"처리 완료: {success_count}/{len(pdf_blobs)}개 성공")

def process_specific_pdf_blob(pdf_blob_name):
    """특정 PDF blob 처리"""
    # blob 이름에 .pdf 확장자가 없으면 추가
    if not pdf_blob_name.lower().endswith('.pdf'):
        pdf_blob_name += '.pdf'
    
    # blob 존재 여부 확인
    try:
        blob_client = container_client.get_blob_client(pdf_blob_name)
        blob_client.get_blob_properties()
        process_pdf_blob(pdf_blob_name)
    except AzureError as e:
        print(f"PDF 파일을 찾을 수 없습니다: {pdf_blob_name}")
        print(f"오류: {e}")

def main():
    print("Azure Storage PDF 처리 도구")
    print("=" * 50)
    
    while True:
        print("\n처리 옵션을 선택하세요:")
        print("1. 모든 PDF 파일 처리")
        print("2. 특정 PDF 파일 처리")
        print("3. PDF 파일 목록 보기")
        print("4. 종료")
        
        choice = input("선택 (1-4): ").strip()
        
        if choice == '1':
            process_all_pdf_blobs()
        elif choice == '2':
            pdf_name = input("처리할 PDF 파일명을 입력하세요 (확장자 포함): ").strip()
            if pdf_name:
                process_specific_pdf_blob(pdf_name)
            else:
                print("파일명을 입력해주세요.")
        elif choice == '3':
            pdf_blobs = list_pdf_blobs()
            if pdf_blobs:
                print(f"\n발견된 PDF 파일: {len(pdf_blobs)}개")
                for i, pdf_blob in enumerate(pdf_blobs, 1):
                    print(f"{i}. {pdf_blob}")
            else:
                print("PDF 파일이 없습니다.")
        elif choice == '4':
            print("프로그램을 종료합니다.")
            break
        else:
            print("잘못된 선택입니다. 다시 선택해주세요.")

if __name__ == "__main__":
    main()