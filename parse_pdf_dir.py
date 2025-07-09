import os
import time
import openai
from dotenv import load_dotenv
import fitz  # PyMuPDF
from openai import AzureOpenAI

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

def extract_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    text = "\n".join([page.get_text() for page in doc])
    doc.close()
    return text

def summarize_to_markdown(text):
    try:
        #prompt = f"""다음은 PDF에서 추출한 과거 서비스운영 관련 및 상용서버 작업내용입니다. 이 내용을 Markdown 형식 파일로 변환해주세요. 내용을 정리해서 요약해도 되지만 누락하거나 생략하지 말아주세요.:\n\n{text}"""    
        prompt = f"""다음은 PDF에서 추출한 인터페이스 정의서 내용입니다. 이 내용을 Markdown 형식 파일로 변환해주세요. 내용을 정리해서 요약해도 되지만 누락하거나 생략하지 말아주세요. 누락없이 모든 API에 대해 Request 와 Response 의 샘플 json도 함께 작성해줘. 양이 방대하여 한번에 처리가 어렵다면 여러번에 나누어 생성해줘.:\n\n{text}"""
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            model=azure_deployment_name
        )
        return response.choices[0].message.content
    except openai.error.RateLimitError as e:
        print(f"요청이 너무 많습니다. 잠시 후 다시 시도해주세요. 오류: {e}")
        time.sleep(60)

def process_pdf_folder(folder_path):
    markdown_dir = os.path.join(folder_path, "markdown")
    os.makedirs(markdown_dir, exist_ok=True)

    for file in os.listdir(folder_path):
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(folder_path, file)
            print(f"처리 중: {file}")

            text = extract_pdf_text(pdf_path)
            markdown_text = summarize_to_markdown(text)

            md_filename = os.path.splitext(file)[0] + ".md"
            md_path = os.path.join(markdown_dir, md_filename)

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)

            print(f"저장 완료: {md_path}")

def main():  
    user_path = input("PDF 파일들이 있는 폴더 경로를 입력하세요: ").strip()
    if os.path.isdir(user_path):
        process_pdf_folder(user_path)
    else:
        print("유효한 경로가 아닙니다. 다시 확인해주세요.")    


if __name__ == "__main__":
    main()