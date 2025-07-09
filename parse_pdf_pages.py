import os
import time
import openai
from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import AzureOpenAI

# 환경변수 로드
load_dotenv()

# Azure OpenAI 설정
azure_api_key = os.getenv("OPENAI_API_KEY")
azure_endpoint = os.getenv("OPENAI_ENDPOINT")
azure_api_version = os.getenv("OPENAI_API_VERSION")
azure_deployment_name = os.getenv("OPENAI_CHAT_DEPLOYMENT_NAME")

# OpenAI 클라이언트 초기화
try:
    client = AzureOpenAI(
        api_version=azure_api_version,
        azure_endpoint=azure_endpoint,
        api_key=azure_api_key
    )
except Exception as e:
    print(f"Azure OpenAI 클라이언트 초기화 중 오류 발생: {e}")
    exit()

def extract_text_from_page_range(doc, start_page, end_page):
    """PDF 문서의 특정 페이지 범위에서 텍스트를 추출합니다."""
    text = ""
    # 실제 페이지 범위에 맞게 반복
    for page_num in range(start_page, min(end_page, len(doc))):
        page = doc.load_page(page_num)
        text += page.get_text() + "\n"
    return text

def summarize_to_markdown(text_chunk):
    """텍스트 묶음을 OpenAI를 통해 마크다운으로 변환합니다."""
    if not text_chunk or not text_chunk.strip():
        return ""
    try:
        prompt = f"""다음은 PDF에서 추출한 인터페이스 정의서 내용의 일부입니다. 이 내용을 Markdown 형식으로 변환해주세요. 내용을 정리하고 요약할 수 있지만, 중요한 정보는 누락하지 말아주세요. 모든 API에 대한 Request와 Response의 샘플 JSON을 포함해 작성해주세요.:\n\n{text_chunk}"""
        
        response = client.chat.completions.create(
            model=azure_deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return response.choices[0].message.content
    except openai.RateLimitError as e:
        print(f"API 요청 한도를 초과했습니다. 60초 후 다시 시도합니다. 오류: {e}")
        time.sleep(60)
        return summarize_to_markdown(text_chunk)  # 재시도
    except Exception as e:
        print(f"마크다운 변환 중 오류 발생: {e}")
        return ""

def process_large_pdf_in_chunks(pdf_path, chunk_size):
    """대용량 PDF 파일을 페이지 묶음 단위로 처리하여 여러 마크다운 파일로 저장합니다."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"PDF 파일을 여는 중 오류 발생: {e}")
        return

    total_pages = len(doc)
    if total_pages == 0:
        print("PDF 파일에 내용이 없습니다.")
        doc.close()
        return

    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    output_dir = os.path.join(os.path.dirname(pdf_path), f"{base_filename}_markdown_parts")
    os.makedirs(output_dir, exist_ok=True)
    print(f"마크다운 파일은 '{output_dir}' 폴더에 저장됩니다.\n")

    # 페이지 묶음 단위로 PDF 처리
    for i in range(0, total_pages, chunk_size):
        start_page = i
        end_page = i + chunk_size
        part_num = (i // chunk_size) + 1
        
        print(f"처리 중: {start_page + 1}페이지 - {min(end_page, total_pages)}페이지 (파일 {part_num})")

        text_chunk = extract_text_from_page_range(doc, start_page, end_page)
        if not text_chunk.strip():
            print(f"  -> 해당 페이지에 텍스트가 없어 건너뜁니다.")
            continue

        markdown_content = summarize_to_markdown(text_chunk)
        if not markdown_content:
            print(f"  -> 마크다운 변환에 실패했습니다 (파일 {part_num}).")
            continue

        md_filename = f"{base_filename}_part_{part_num}.md"
        md_path = os.path.join(output_dir, md_filename)
        
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"  -> 저장 완료: {md_path}")
        except Exception as e:
            print(f"  -> 파일 저장 중 오류 발생: {e}")

    doc.close()
    print("\n모든 작업이 완료되었습니다.")

def main():
    pdf_path = input("분할 변환할 대용량 PDF 파일의 경로를 입력하세요: ").strip()
    if not os.path.isfile(pdf_path) or not pdf_path.lower().endswith(".pdf"):
        print("유효한 PDF 파일 경로가 아닙니다. 프로그램을 종료합니다.")
        return
        
    while True:
        try:
            chunk_size_str = input("한 번에 처리할 페이지 수를 입력하세요 (예: 5): ").strip()
            chunk_size = int(chunk_size_str)
            if chunk_size > 0:
                break
            else:
                print("페이지 수는 1 이상의 숫자여야 합니다.")
        except ValueError:
            print("유효한 숫자를 입력해주세요.")

    process_large_pdf_in_chunks(pdf_path, chunk_size)

if __name__ == "__main__":
    main()
