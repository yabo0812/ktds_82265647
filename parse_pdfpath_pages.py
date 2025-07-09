import os
import time
import openai
from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import AzureOpenAI
import json
import hashlib
from PIL import Image
import io

# 환경변수 
load_dotenv()
# Azure OpenAI 설정
azure_api_key = os.getenv("OPENAI_API_KEY")
azure_endpoint = os.getenv("OPENAI_ENDPOINT") # Azure OpenAI 엔드포인트
azure_api_version = os.getenv("OPENAI_API_VERSION")  # Azure OpenAI API 버전
azure_deployment_name = os.getenv("OPENAI_CHAT_DEPLOYMENT_NAME")   # Azure OpenAI 배포된 모델 이름

# OpenAI 클라이언트 초기화
client = AzureOpenAI(
    api_version=azure_api_version,
    azure_endpoint=azure_endpoint,
    api_key=azure_api_key
)

def extract_images_from_pdf(pdf_path, output_dir, pdf_name):
    """PDF에서 이미지를 추출하고 저장"""
    doc = fitz.open(pdf_path)
    image_info = []
     
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
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
                img_path = os.path.join(images_dir, img_filename)
                
                # 이미지 저장
                with open(img_path, "wb") as img_file:
                    img_file.write(image_bytes)
                
                # 이미지 정보 저장
                image_info.append({
                    "page_num": page_num + 1,
                    "img_index": img_index + 1,
                    "filename": img_filename,
                    "path": img_path,
                    "hash": img_hash
                })
                
                print(f"이미지 저장: {img_filename}")
                
            except Exception as e:
                print(f"이미지 추출 오류 (페이지 {page_num + 1}, 이미지 {img_index + 1}): {e}")
    
    doc.close()
    return image_info

def extract_pdf_text_with_pages(pdf_path):
    """PDF에서 페이지별로 텍스트 추출"""
    doc = fitz.open(pdf_path)
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
                images_text += f"- 페이지 {img['page_num']}: {img['filename']}\n"
        
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
            temperature=0.1,  # 일관성을 위해 낮은 온도 설정
            model=azure_deployment_name,
            max_tokens=4000  # 충분한 토큰 수 설정
        )
        return response.choices[0].message.content
    except openai.error.RateLimitError as e:
        print(f"요청이 너무 많습니다. 잠시 후 다시 시도해주세요. 오류: {e}")
        time.sleep(60)
        return summarize_to_markdown(text, chunk_info, chunk_images)  # 재시도
    except Exception as e:
        print(f"마크다운 변환 오류: {e}")
        return None

def create_metadata_file(output_dir, pdf_name, chunks_info, image_info):
    """메타데이터 파일 생성 (검색 시 참조용)"""
    metadata = {
        "pdf_name": pdf_name,
        "total_chunks": len(chunks_info),
        "chunks": chunks_info,
        "images": image_info,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    metadata_path = os.path.join(output_dir, f"{pdf_name}_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    return metadata_path

def process_pdf_folder(folder_path):
    """PDF 폴더 처리"""
    markdown_dir = os.path.join(folder_path, "markdown")
    os.makedirs(markdown_dir, exist_ok=True)

    for file in os.listdir(folder_path):
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, file)
            pdf_name = os.path.splitext(file)[0]
            print(f"처리 중: {file}")

            # 1. 이미지 추출
            print("이미지 추출 중...")
            image_info = extract_images_from_pdf(pdf_path, markdown_dir, pdf_name)
            print(f"추출된 이미지 수: {len(image_info)}")

            # 2. 페이지별 텍스트 추출
            print("텍스트 추출 중...")
            pages_text = extract_pdf_text_with_pages(pdf_path)
            total_pages = len(pages_text)
            print(f"총 페이지 수: {total_pages}")

            # 3. 페이지 청크 분할
            chunks = create_page_chunks(pages_text, chunk_size=40)
            print(f"생성된 청크 수: {len(chunks)}")

            # 4. 각 청크를 마크다운으로 변환
            chunks_info = []
            for chunk in chunks:
                chunk_images = get_images_for_chunk(image_info, chunk["start_page"], chunk["end_page"])
                
                print(f"청크 {chunk['chunk_index'] + 1} 변환 중 (페이지 {chunk['start_page']}-{chunk['end_page']})")
                markdown_text = summarize_to_markdown(chunk["text"], chunk, chunk_images)
                
                if markdown_text:
                    # 청크별 마크다운 파일 저장
                    if len(chunks) == 1:
                        md_filename = f"{pdf_name}.md"
                    else:
                        md_filename = f"{pdf_name}_part{chunk['chunk_index'] + 1}_pages{chunk['start_page']}-{chunk['end_page']}.md"
                    
                    md_path = os.path.join(markdown_dir, md_filename)
                    
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(markdown_text)
                    
                    chunks_info.append({
                        "chunk_index": chunk['chunk_index'],
                        "start_page": chunk['start_page'],
                        "end_page": chunk['end_page'],
                        "filename": md_filename,
                        "path": md_path,
                        "images": chunk_images
                    })
                    
                    print(f"저장 완료: {md_path}")
                    
                    # API 호출 간격 조절
                    time.sleep(2)
                else:
                    print(f"청크 {chunk['chunk_index'] + 1} 변환 실패")

            # 5. 메타데이터 파일 생성
            metadata_path = create_metadata_file(markdown_dir, pdf_name, chunks_info, image_info)
            print(f"메타데이터 저장: {metadata_path}")
            
            print(f"'{file}' 처리 완료!\n")

def main():  
    user_path = input("PDF 파일들이 있는 폴더 경로를 입력하세요: ").strip()
    if os.path.isdir(user_path):
        process_pdf_folder(user_path)
    else:
        print("유효한 경로가 아닙니다. 다시 확인해주세요.")    

if __name__ == "__main__":
    main()