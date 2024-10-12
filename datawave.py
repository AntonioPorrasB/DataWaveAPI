import re
import requests
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from groq import Groq

app = FastAPI()
app.title="DataWave App"
app.version="3.0.0"

client = Groq(api_key="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")

# Configurar CORS para permitir peticiones desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cambia "*" por el dominio del frontend en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de entrada para la URL de la publicación
class FacebookPost(BaseModel):
    link: str

def get_facebook_comments(post_url):
    access_token = 'EAANInzT2Im8BO3aSNZB58ZAwSTaTTb3TRxTGQYWvQnk1IPv50oK6G35RW2EcRaOvkTIAazHRVWZCT9pnCCcKbWFPNaC21Ovmbh6MQSZAAlVj9QAoTLLuFvDTD09MX4AYGXoImvC7Xbn7JJhaeUrBLZCy01FRCrSXrfZAK06n3u0TiXr0ZCYD7gieaUJbWdZBXT3i'
    post_id_match = re.search(r"=(\d+)", post_url)
    if not post_id_match:
        raise HTTPException(status_code=400, detail="No se pudo extraer el post_id de la URL.")
    
    post_id = post_id_match.group(1)
    comments = []
    url = f'https://graph.facebook.com/v20.0/{post_id}/comments?fields=message&access_token={access_token}&summary=true'
    
    while url:
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Error fetching comments: {response.status_code}")
        
        data = response.json()
        comments.extend([comment['message'] for comment in data['data']])
        url = data.get('paging', {}).get('next')
    
    return comments

def clean_comments(comments):
    cleaned_comments = []
    for comment in comments:
        comment = re.sub(r"[\U00010000-\U0010ffff]", "", comment)
        comment = re.sub(r"http\S+|www\S+|https\S+", "", comment)
        comment = re.sub(r"[^\w\s]", "", comment)
        comment = re.sub(r"\s+", " ", comment)
        comment = comment.lower()
        cleaned_comments.append(comment)
    return cleaned_comments

def get_ai_response(messages):
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
            stream=False,
        )
        if hasattr(completion, 'choices') and len(completion.choices) > 0:
            response = completion.choices[0].message.content
        else:
            response = "Error al obtener respuesta de la IA."
    except Exception as e:
        response = f"Error: {e}"
    return response

def analyze_sentiment_in_batches(cleaned_comments, batch_size=50):
    all_responses = []
    comment_classifications = []  # Aquí guardaremos los comentarios y sus clasificaciones
    num_comments = len(cleaned_comments)
    
    for i in range(0, num_comments, batch_size):
        batch = cleaned_comments[i:i + batch_size]
        
        prompt = "Clasifica los siguientes comentarios como positivos o negativos, solamente pon el comentario seguido de si es positivo o negativo de esta forma 'comentario: positivo', no pongas nada más:\n"
        for idx, comment in enumerate(batch, 1):
            prompt += f"{idx}. {comment}\n"
        
        messages = [{"role": "user", "content": prompt}]
        ai_response = get_ai_response(messages)
        
        # Divide la respuesta en líneas y asigna la clasificación
        for line in ai_response.splitlines():
            if ": positivo" in line:
                comment_classifications.append({
                    "comment": line.split(":")[0].strip(),
                    "sentiment": "positivo"
                })
            elif ": negativo" in line:
                comment_classifications.append({
                    "comment": line.split(":")[0].strip(),
                    "sentiment": "negativo"
                })

        all_responses.append(ai_response)
        time.sleep(2)
    
    return comment_classifications

@app.post("/analyze")
def analyze(post: FacebookPost):
    comments = get_facebook_comments(post.link)
    cleaned_comments = clean_comments(comments)

    classified_comments = analyze_sentiment_in_batches(cleaned_comments)

    positive_count = sum(1 for c in classified_comments if c['sentiment'] == "positivo")
    negative_count = sum(1 for c in classified_comments if c['sentiment'] == "negativo")

    return {
        "negative_count": negative_count,
        "positive_count": positive_count,
        "classified_comments": classified_comments
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("datawave:app", host="0.0.0.0", port=8000, reload=True)