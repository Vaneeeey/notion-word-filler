# fill_words.py
import os, pathlib, time, requests
from dotenv import load_dotenv
from openai import OpenAI          # 官方 openai 库同样适用硅基流动

# ---------- 环境变量 ----------
env_path = pathlib.Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)   # 显式指定路径，避免找不到
SF_API_KEY   = os.getenv("SF_API_KEY")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID  = os.getenv("DATABASE_ID")

# ---------- 硅基流动客户端 ----------
client = OpenAI(
    api_key = SF_API_KEY,
    base_url = "https://api.siliconflow.cn/v1"
)

# ---------- Notion 头信息 ----------
NOTION_HDRS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# ---------- 1) 取 Definition 为空的行 ----------
def fetch_blank_rows(limit=1):
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {"property": "Definition", "rich_text": {"is_empty": True}},
        "page_size": limit
    }
    res = requests.post(url, json=payload, headers=NOTION_HDRS, timeout=30)
    res.raise_for_status()
    return res.json()["results"]

# ---------- 2) 调硅基流动获取定义/同/反义词 ----------
import json

def enrich_word(word: str) -> tuple[str, str, str]:
    prompt = (
        f"请以 JSON 格式返回 IELTS 单词“{word}”的信息，严格不要换行、不要其他字符：\n"
        f'{{"definition": "<中文详解，可含多个词性；例：v. （使）发芽；开始生长>", '
        f'"synonyms": ["syn1", "syn2", "syn3"], '
        f'"antonyms": ["ant1", "ant2", "ant3"]}}'
    )
    resp = client.chat.completions.create(
        model="Qwen/Qwen2.5-7B-Instruct",
        messages=[{"role": "user", "content": prompt}],
        timeout=30
    ).choices[0].message.content.strip()

    # 有时模型会包在 ```json ``` 代码块里，先剥掉
    resp = resp.strip("`").lstrip("json").strip("`").strip()
    data = json.loads(resp)

    definition = data.get("definition", "-")
    synonyms   = ", ".join(data.get("synonyms", [])) or "-"
    antonyms   = ", ".join(data.get("antonyms", [])) or "-"
    return definition, synonyms, antonyms

# ---------- 3) 写回 Notion ----------
def write_back(page_id: str, definition: str, synonyms: str, antonyms: str):
    def rt(text):          # 生成 rich_text 数组
        return {"rich_text": [{"text": {"content": text}}]} if text else {"rich_text": []}

    payload = {
        "properties": {
            "Definition": rt(definition),
            "Synonyms":   rt(synonyms),
            "Antonyms":   rt(antonyms)
        }
    }
    url = f"https://api.notion.com/v1/pages/{page_id}"
    res = requests.patch(url, json=payload, headers=NOTION_HDRS, timeout=30)
    res.raise_for_status()

# ---------- 主流程：只处理 1 行，便于测试 ----------
if __name__ == "__main__":
    pages = fetch_blank_rows(limit=500)
    if not pages:
        print(">>> 数据库暂时没有空 Definition 的单词。")
    else:
        for page in pages:
            word = page["properties"]["Name"]["title"][0]["plain_text"]
            print(f"[*] 正在处理：{word}")
            definition, synonyms, antonyms = enrich_word(word)
            write_back(page["id"], definition, synonyms, antonyms)
            time.sleep(1.2)          # 避免速率限制
        print(">>> 本轮已写回", len(pages), "条记录！")