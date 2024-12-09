import re
import requests
import time
import os  # Asegúrate de importar os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from groq import Groq
from collections import Counter

app = FastAPI()
app.title = "DataWave App"
app.version = "3.5.0"

client = Groq(api_key="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")

# Configurar CORS para permitir peticiones desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Cambia esto por el puerto que uses para tu frontend local
        "http://localhost:8000", # Para tu frontend local (ej. React, Vue, etc.)
        "https://datawaveapi.onrender.com",
        "https://softwave-innovate.tech",
        "https://softwaveapi.onrender.com"],  # Cambia "*" por el dominio del frontend en producción
        
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de entrada para la URL de la publicación
class FacebookPost(BaseModel):
    link: str

temas_relevantes = {
    "Servicio al Cliente": ["servicio", "atención", "cliente", "soporte"],
    "Calidad del Producto": ["calidad", "producto", "bueno", "defectuoso"],
    "Experiencia de Usuario": ["experiencia", "usuario", "amigable", "complicado"],
    "Precio": ["precio", "costo", "económico", "caro"]
}

excluded_words = [
    "de", "la", "es", "y", "en", "que", "el", "a", "los", "con", "por", "un", "una", "este", "esta", "esto", "mi", "me",
    "lo", "estoy", "mí", "las", "son", "he", "alguien", "no", "ha",
]

@app.get("/")
async def read_root():
    return {"message": "DataWave API is running."}

def get_facebook_comments(post_url):
    #EAANInzT2Im8BOZCM7Omj3hxGAHN8ZAgvBIvU1NQI99nsn1wMZBohHqX29K5TWLeMoYFjXDSZAwQhCvEsMeloCFaYkUf7hRrBO2RpPh5RSUY8CTE6KtiQlMDN7rKhkNADzMYZAznREsTZCblIhkZCYeaPmkRilZAXZBvoCA0EnW3fYbrwfMUcDOW8CsZClhnjWGKkhND0BNE9WzNJNSZB8qXIZCrmgvqV
    access_token = 'EAANInzT2Im8BO7mXxHYTu6Uy36TZAzaxgQQPckyLCNPU9UDHTYQ8OvQWdgayw1hU5rx52RzH1hbHZCN1x2AtnGI1hpI2UIzc1Sd04yB9Ff5WovfiaZBzzo51jCZCRWm83Si1Aqr9KiDk4HbQSiCyo4X96tJDRbdWZAGCca5hdOaJJqDQGapoA4HUtmxYeJM6M'
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

def classify_comments_by_topics(cleaned_comments):
    topic_counts = {topic: 0 for topic in temas_relevantes.keys()}
    topic_counts["Otro"] = 0

    for comment in cleaned_comments:
        matched = False
        for topic, keywords in temas_relevantes.items():
            if any(keyword in comment for keyword in keywords):
                topic_counts[topic] += 1
                matched = True
                break
        if not matched:
            topic_counts["Otro"] += 1

    return topic_counts

def get_most_frequent_words(cleaned_comments, min_frequency=3):
    words = [word for comment in cleaned_comments for word in comment.split() if word not in excluded_words]
    word_counts = Counter(words)
    return {word: count for word, count in word_counts.items() if count >= min_frequency}

@app.post("/analyze")
def analyze(post: FacebookPost):
    comments = get_facebook_comments(post.link)
    cleaned_comments = clean_comments(comments)

    classified_comments = analyze_sentiment_in_batches(cleaned_comments)

    positive_count = sum(1 for c in classified_comments if c['sentiment'] == "positivo")
    negative_count = sum(1 for c in classified_comments if c['sentiment'] == "negativo")
    topic_counts = classify_comments_by_topics(cleaned_comments)
    frequent_words = get_most_frequent_words(cleaned_comments)
    
    # Convertir el recuento de temas en una lista de objetos
    topics_list = [{"name": key, "count": value} for key, value in topic_counts.items()]
    words_list = [{"word": word, "count": count} for word, count in frequent_words.items()]

    return {
        "negative_count": negative_count,
        "positive_count": positive_count,
        "classified_comments": classified_comments,
        "topics": topics_list,
        "frequent_words": words_list,
        
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Cambia a usar la variable de entorno PORT
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
