import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

subscription_key = os.getenv("AZURE_OPENAI_API_KEY")
endpoint =os.getenv("AZURE_OPENAI_ENDPOINT")
api_version = os.getenv("AZURE_OPENAI_CHAT_API_VERSION")
deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

# Initialize the Azure OpenAI client
client = AzureOpenAI(
    api_key=subscription_key,
    azure_endpoint=endpoint,
    api_version=api_version,
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "당신은 리눅스 명령어와 쉘 스크립트 전문가입니다. 사용자의 질문에 대해 전문가 수준의 정확한 정보를 한국어로 제공해 주세요. 필요한 경우 코드 예시를 포함해 주세요. 당신의 전문분야 외의 정보는 전혀 모릅니다. ",
        },
        {            
            "role": "user",
            "content": "매일 /log 경로에 생성된지 10일 경과된 파일들을 gzip으로 압축하고, 압축된 파일은 /log/archived 경로에 저장하는 쉘 스크립트를 작성해 주세요."+
                       " 압축 후 원본 파일은 삭제해야 합니다.",
        },
    ],
    max_completion_tokens=800,
    temperature=1.0,
    top_p=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    model=deployment
)

print(response.choices[0].message.content)