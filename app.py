import os
import re
import pathlib
import tempfile

import fitz
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import speech_recognition as sr
import streamlit as st
import streamlit.components.v1 as components

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# =========================================================
# CONFIGURATION
# =========================================================
MODEL_PATH = "ai_mock_interview_champion_model.pkl"
QUESTIONS_PATH = "questions.csv"

FEATURE_COLUMNS = [
    "answer_length",
    "keyword_coverage",
    "tfidf_similarity",
    "semantic_similarity",
    "concept_coverage",
    "relevance_score",
]

SAPLING_URL = "https://api.sapling.ai/api/v1/aidetect"

st.set_page_config(
    page_title="AI Mock Interview Analyzer",
    layout="wide",
)

try:
    SAPLING_API_KEY = st.secrets.get("SAPLING_API_KEY", "")
except Exception:
    SAPLING_API_KEY = os.getenv("SAPLING_API_KEY", "")


# =========================================================
# SAPLING AI DETECTION
# =========================================================
def detect_ai_sapling(answer: str) -> dict:
    if not answer or len(answer.split()) < 4:
        return {
            "score": 0.0,
            "label": "Answer Too Short",
            "reasons": ["Answer is too short for a meaningful check."],
        }

    if not SAPLING_API_KEY:
        return {
            "score": 0.0,
            "label": "API Key Missing",
            "reasons": ["SAPLING_API_KEY is not configured in Streamlit Secrets."],
        }

    try:
        response = requests.post(
            SAPLING_URL,
            json={"key": SAPLING_API_KEY, "text": answer},
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "score": 0.0,
                "label": "Detection Unavailable",
                "reasons": [f"Sapling returned HTTP {response.status_code}."],
            }

        data = response.json()
        overall_score = float(data.get("score", 0.0))

        sentence_scores = []
        for item in data.get("sentence_scores", []):
            if isinstance(item, dict) and "score" in item:
                sentence_scores.append(float(item["score"]))
            elif isinstance(item, (int, float)):
                sentence_scores.append(float(item))

        effective_score = max([overall_score] + sentence_scores)
        ai_score = round(float(np.clip(effective_score * 100, 0, 100)), 1)

        if ai_score >= 50:
            label = "AI Assistance Suspected"
        elif ai_score >= 25:
            label = "Possible AI Assistance"
        else:
            label = "No Strong AI Pattern"

        return {
            "score": ai_score,
            "label": label,
            "reasons": [f"Sapling AI confidence: {ai_score:.1f}%"],
        }

    except requests.RequestException as exc:
        return {
            "score": 0.0,
            "label": "Detection Unavailable",
            "reasons": [f"Sapling request failed: {exc.__class__.__name__}"],
        }
    except (ValueError, TypeError):
        return {
            "score": 0.0,
            "label": "Detection Unavailable",
            "reasons": ["Sapling returned an invalid response."],
        }


# =========================================================
# WINDOW SWITCH MONITOR
# =========================================================
COMPONENT_DIR = pathlib.Path(__file__).parent / "window_switch_component"

if COMPONENT_DIR.exists():
    WINDOW_SWITCH_MONITOR = components.declare_component(
        "window_switch_monitor",
        path=str(COMPONENT_DIR),
    )
else:
    WINDOW_SWITCH_MONITOR = None


def detect_window_switch() -> int:
    if WINDOW_SWITCH_MONITOR is None:
        st.warning(
            "Window-switch component folder was not found. "
            "Window-switch monitoring is currently unavailable."
        )
        return int(st.session_state.window_switch_count)

    reported_count = WINDOW_SWITCH_MONITOR(
        current_count=st.session_state.window_switch_count,
        reset_token=st.session_state.interview_id,
        key=f"window_switch_monitor_{st.session_state.interview_id}",
        default=st.session_state.window_switch_count,
        height=0,
    )

    if isinstance(reported_count, (int, float)):
        st.session_state.window_switch_count = max(
            st.session_state.window_switch_count,
            int(reported_count),
        )

    if st.session_state.window_switch_count >= 2:
        st.session_state.disqualified = True

    return int(st.session_state.window_switch_count)


# =========================================================
# MODEL AND DATASET LOADING
# =========================================================
@st.cache_resource
def load_assets():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model file '{MODEL_PATH}' was not found in the app folder."
        )

    if not os.path.exists(QUESTIONS_PATH):
        raise FileNotFoundError(
            f"Dataset '{QUESTIONS_PATH}' was not found in the app folder."
        )

    model = joblib.load(MODEL_PATH)
    questions = pd.read_csv(QUESTIONS_PATH)

    required_columns = {
        "job_roles",
        "category",
        "difficulty",
        "question",
        "expected_concepts",
    }

    missing = required_columns.difference(questions.columns)

    if missing:
        raise ValueError(
            "questions.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )

    model_feature_count = getattr(model, "n_features_in_", None)

    if model_feature_count is not None and model_feature_count != len(FEATURE_COLUMNS):
        raise ValueError(
            f"The model expects {model_feature_count} features, but this app "
            f"provides {len(FEATURE_COLUMNS)}."
        )

    model_feature_names = getattr(model, "feature_names_in_", None)

    if model_feature_names is not None:
        model_feature_names = list(model_feature_names)

        if model_feature_names != FEATURE_COLUMNS:
            raise ValueError(
                "Model feature names/order do not match app feature order.\n"
                f"Model: {model_feature_names}\n"
                f"App: {FEATURE_COLUMNS}"
            )

    return model, questions


try:
    eval_model, questions_df = load_assets()
except Exception as exc:
    st.error(f"Initialization Error: {exc}")
    st.stop()


# =========================================================
# PAGE STYLING
# =========================================================
st.markdown(
    """
    <style>
    .question-box {
        background-color: #f0f7f7;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 15px;
        border-left: 6px solid #008080;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("≡ƒÄÖ∩╕Å AI Mock Interview Analyzer")
st.caption(
    "Resume-aware technical interview system with speech-to-text, "
    "trained ML scoring, and Sapling AI Detection"
)


# =========================================================
# DOMAIN TAXONOMY
# =========================================================
DOMAIN_TAXONOMY = {
    "AI Engineer": [
        "Deep Learning", "Transformers", "Computer Vision",
        "Generative AI", "NLP", "BERT", "PyTorch",
        "TensorFlow", "Diffusion", "Reinforcement Learning", "LLM",
    ],
    "Machine Learning / Data Science": [
        "Machine Learning", "Scikit-learn", "Random Forest",
        "XGBoost", "SVM", "Statistics", "Hypothesis Testing",
        "Pandas", "NumPy", "Regression", "Clustering",
    ],
    "Computer Science Core": [
        "Data Structures", "Algorithms", "Operating Systems",
        "DBMS", "SQL", "Computer Networks", "System Design",
        "C++", "Java", "Linux", "Concurrency",
    ],
}


# =========================================================
# RESUME EXTRACTION AND ANALYSIS
# =========================================================
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        return "\n".join(
            page.get_text("text") for page in document
        ).strip()
    finally:
        document.close()


def analyze_resume(text: str) -> dict:
    clean = text.lower()

    scores = {
        domain: sum(
            bool(re.search(r"\b" + re.escape(skill.lower()) + r"\b", clean))
            for skill in skills
        )
        for domain, skills in DOMAIN_TAXONOMY.items()
    }

    detected_domain = (
        max(scores, key=scores.get)
        if any(scores.values())
        else "Computer Science Core"
    )

    email_match = re.search(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        text,
    )

    phone_match = re.search(
        r"(?:\+?\d{1,3}[-.\s]?)?\d{10}",
        text,
    )

    first_line = (
        text.strip().split("\n")[0].strip()
        if text.strip()
        else ""
    )

    return {
        "name": first_line if len(first_line) < 35 and first_line else "Candidate",
        "email": email_match.group(0) if email_match else "N/A",
        "phone": phone_match.group(0) if phone_match else "N/A",
        "detected_domain": detected_domain,
    }


# =========================================================
# SPEECH TO TEXT
# =========================================================
def convert_audio_to_text(audio_bytes: bytes) -> str:
    recognizer = sr.Recognizer()
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False
        ) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)

        return recognizer.recognize_google(audio_data).strip()

    except sr.UnknownValueError:
        return ""

    except sr.RequestError:
        st.warning(
            "Speech recognition service is currently unavailable."
        )
        return ""

    except Exception:
        return ""

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# =========================================================
# NLP FEATURE ENGINEERING
# Feature names and order match the new StackingRegressor.
# =========================================================
def calculate_nlp_features(answer: str, expected: str):
    answer_tokens = [
        word.lower()
        for word in re.findall(r"\b\w+\b", answer)
        if len(word) > 1
    ]

    expected_tokens = [
        word.lower()
        for word in re.findall(r"\b\w+\b", expected)
    ]

    answer_length = len(answer_tokens)

    if expected_tokens:
        concept_coverage = (
            sum(token in answer_tokens for token in expected_tokens)
            / len(expected_tokens)
        )
    else:
        concept_coverage = 0.5

    try:
        tfidf_matrix = TfidfVectorizer().fit_transform(
            [expected, answer]
        )

        tfidf_similarity = float(
            cosine_similarity(
                tfidf_matrix[0:1],
                tfidf_matrix[1:2],
            )[0][0]
        )

    except ValueError:
        tfidf_similarity = 0.0

    semantic_similarity = float(
        np.clip(
            0.55 * tfidf_similarity + 0.45 * concept_coverage,
            0,
            1,
        )
    )

    relevance_score = float(
        0.4 * tfidf_similarity + 0.6 * semantic_similarity
    )

    keyword_coverage = float(
        concept_coverage * 0.92
        + 0.08 * min(1, answer_length / 35)
    )

    feature_values = [[
        answer_length,
        keyword_coverage,
        tfidf_similarity,
        semantic_similarity,
        concept_coverage,
        relevance_score,
    ]]

    feature_frame = pd.DataFrame(
        feature_values,
        columns=FEATURE_COLUMNS,
    )

    metrics = {
        "relevance": relevance_score,
        "concept_coverage": concept_coverage,
        "tfidf_similarity": tfidf_similarity,
        "semantic_similarity": semantic_similarity,
        "answer_length": answer_length,
        "keyword_coverage": keyword_coverage,
    }

    return feature_frame, metrics


def predict_answer_score(
    model,
    feature_frame: pd.DataFrame
) -> float:

    prediction = model.predict(feature_frame)

    return float(
        np.clip(float(prediction[0]), 0, 100)
    )


# =========================================================
# SESSION STATE
# =========================================================
DEFAULTS = {
    "interview_started": False,
    "current_q_idx": 0,
    "selected_questions": [],
    "evaluations": [],
    "profile": None,
    "window_switch_count": 0,
    "disqualified": False,
    "interview_id": 0,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =========================================================
# SCREEN 1: RESUME UPLOAD
# =========================================================
if not st.session_state.interview_started:

    st.subheader(
        "≡ƒôä Step 1: Candidate Verification & Resume Analysis"
    )

    uploaded_pdf = st.file_uploader(
        "Upload candidate resume (PDF format)",
        type=["pdf"],
    )

    if uploaded_pdf is not None:

        try:
            with st.spinner("Analyzing resume content..."):

                profile = analyze_resume(
                    extract_text_from_pdf(
                        uploaded_pdf.getvalue()
                    )
                )

                st.session_state.profile = profile

            st.success(
                f"Candidate: **{profile['name']}** | "
                f"Domain: **{profile['detected_domain']}**"
            )

            tracks = [
                "AI Engineer",
                "Machine Learning / Data Science",
                "Computer Science Core",
            ]

            target = st.selectbox(
                "Confirm Technical Interview Track:",
                tracks,
                index=tracks.index(profile["detected_domain"]),
            )

            number_of_questions = st.slider(
                "Number of Questions:",
                min_value=3,
                max_value=7,
                value=4,
            )

            if st.button(
                "Enter Interview Room",
                type="primary"
            ):

                patterns = {
                    "AI Engineer": r"AI Engineer|Deep Learning",

                    "Machine Learning / Data Science":
                        r"Data Scientist|Machine Learning",

                    "Computer Science Core":
                        r"Computer Science Core|Software Engineer",
                }

                matched = questions_df[
                    questions_df["job_roles"].astype(str).str.contains(
                        patterns[target],
                        na=False,
                        case=False,
                        regex=True,
                    )
                ]

                if matched.empty:
                    st.error(
                        "No questions matched this interview track in "
                        "questions.csv. Check the job_roles column."
                    )
                    st.stop()

                selected = matched.sample(
                    n=min(len(matched), number_of_questions)
                )

                st.session_state.profile["target_domain"] = target

                st.session_state.selected_questions = (
                    selected.to_dict("records")
                )

                st.session_state.interview_started = True
                st.session_state.current_q_idx = 0
                st.session_state.evaluations = []
                st.session_state.window_switch_count = 0
                st.session_state.disqualified = False
                st.session_state.interview_id += 1

                st.rerun()

        except Exception as exc:
            st.error(f"Resume analysis error: {exc}")


# =========================================================
# SCREEN 2: INTERVIEW AND EVALUATION
# =========================================================
else:

    questions = st.session_state.selected_questions
    question_index = st.session_state.current_q_idx

    st.sidebar.subheader("Candidate Profile")

    if st.session_state.profile:

        st.sidebar.write(
            f"**Name:** {st.session_state.profile.get('name', 'Candidate')}"
        )

        st.sidebar.write(
            f"**Track:** {st.session_state.profile.get('target_domain', 'N/A')}"
        )

    switch_count = detect_window_switch()

    if st.session_state.disqualified:

        st.error("≡ƒÜ½ INTERVIEW DISQUALIFIED")
        st.title("Interview Cancelled!")

        st.write(
            "You have switched away from the interview window twice. "
            "The interview has been terminated according to the configured rules."
        )

        st.caption(
            "The interview was cancelled after the second detected "
            "browser-tab visibility change."
        )

        st.stop()

    if switch_count == 1:

        st.warning(
            "ΓÜá∩╕Å Window switch detected. Please return to the interview "
            "and remain focused. (1 of 2 allowed switches used.)"
        )

    # =====================================================
    # FINAL SCORECARD
    # =====================================================
    if question_index >= len(questions):

        st.header(
            "≡ƒÅü Interview Evaluation & Performance Report"
        )

        evaluations = st.session_state.evaluations

        scores = [
            item["score"]
            for item in evaluations
        ]

        relevance_scores = [
            item["metrics"]["relevance"] * 100
            for item in evaluations
        ]

        coverage_scores = [
            item["metrics"]["concept_coverage"] * 100
            for item in evaluations
        ]

        ai_scores = [
            item["metrics"].get("ai_assistance_score", 0.0)
            for item in evaluations
        ]

        average_score = (
            float(np.mean(scores)) if scores else 0.0
        )

        average_relevance = (
            float(np.mean(relevance_scores))
            if relevance_scores else 0.0
        )

        average_coverage = (
            float(np.mean(coverage_scores))
            if coverage_scores else 0.0
        )

        average_ai = (
            float(np.mean(ai_scores))
            if ai_scores else 0.0
        )

        if average_ai >= 40:

            st.error(
                f"Γ¥î **STATUS: REVIEW REQUIRED** "
                f"(AI assistance indicator: {average_ai:.1f}%)"
            )

            st.warning(
                "The AI detector flagged the responses. This is an automated "
                "indicator, not definitive proof of AI use; review answers "
                "before making a final decision."
            )

        else:

            st.success(
                f"Γ£à **STATUS: NO HIGH AI-DETECTION FLAG** "
                f"(AI assistance indicator: {average_ai:.1f}%)"
            )

            st.info(
                "The detector did not return a high AI-assistance indicator. "
                "Review the technical scores and answers as part of assessment."
            )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Overall Score",
            f"{average_score:.1f} / 100"
        )

        col2.metric(
            "Concept Coverage",
            f"{average_coverage:.1f}%"
        )

        col3.metric(
            "Semantic Relevance",
            f"{average_relevance:.1f}%"
        )

        col4.metric(
            "Avg AI Detected",
            f"{average_ai:.1f}%"
        )

        chart_col, table_col = st.columns(2)

        with chart_col:

            radar = go.Figure(
                data=go.Scatterpolar(
                    r=[
                        average_score,
                        average_relevance,
                        average_coverage,
                        max(0, 100 - average_ai),
                    ],
                    theta=[
                        "Technical Score",
                        "Relevance",
                        "Concept Coverage",
                        "AI Detector Complement",
                    ],
                    fill="toself",
                    line_color="#008080",
                )
            )

            radar.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100]
                    )
                ),
                showlegend=False,
            )

            st.plotly_chart(
                radar,
                use_container_width=True
            )

        with table_col:

            result_table = pd.DataFrame([
                {
                    "Question": item["question"][:35] + (
                        "..." if len(item["question"]) > 35 else ""
                    ),

                    "Score": f"{item['score']:.1f}",

                    "Concept Match":
                        f"{item['metrics']['concept_coverage'] * 100:.1f}%",

                    "AI Check": (
                        f"{item['metrics'].get('ai_assistance_label', 'N/A')} "
                        f"({item['metrics'].get('ai_assistance_score', 0):.0f}%)"
                    ),
                }

                for item in evaluations
            ])

            st.dataframe(
                result_table,
                use_container_width=True
            )

        if st.button(
            "≡ƒöä Start New Interview",
            type="primary"
        ):

            for key, value in DEFAULTS.items():
                st.session_state[key] = value

            st.rerun()

        st.stop()

    # =====================================================
    # CURRENT QUESTION
    # =====================================================
    current_question = questions[question_index]

    st.progress(
        (question_index + 1) / len(questions)
    )

    st.caption(
        f"Question {question_index + 1} of {len(questions)} | "
        f"Category: {current_question.get('category', 'N/A')} | "
        f"Level: {current_question.get('difficulty', 'N/A')}"
    )

    st.markdown(
        f"""
        <div class="question-box">
            <h3 style="color:#004d40;margin:0;">
                {current_question.get('question', 'Question unavailable')}
            </h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    audio = st.audio_input(
        "Speak your answer using the microphone:",
        key=f"audio_{question_index}",
    )

    typed_answer = st.text_area(
        "Or type your answer directly here:",
        height=120,
        placeholder="Type your answer here...",
        key=f"text_{question_index}",
    )

    if st.button(
        "≡ƒÜÇ Submit & Save Answer",
        type="primary",
        key=f"submit_btn_{question_index}",
    ):

        final_answer = ""

        if audio is not None:

            with st.spinner("≡ƒÄÖ∩╕Å Converting audio to text..."):

                final_answer = convert_audio_to_text(
                    audio.getvalue()
                )

        if not final_answer and typed_answer.strip():
            final_answer = typed_answer.strip()

        if not final_answer or len(final_answer.split()) < 3:

            st.error(
                "Please provide a clear answer with at least 3 words."
            )

        else:

            expected_concepts = str(
                current_question.get("expected_concepts", "")
            )

            try:

                with st.spinner(
                    "New Champion ML model evaluating and checking AI assistance..."
                ):

                    feature_frame, metrics = calculate_nlp_features(
                        final_answer,
                        expected_concepts,
                    )

                    score = predict_answer_score(
                        eval_model,
                        feature_frame,
                    )

                    ai_result = detect_ai_sapling(
                        final_answer
                    )

                metrics["ai_assistance_score"] = ai_result["score"]
                metrics["ai_assistance_label"] = ai_result["label"]
                metrics["ai_assistance_reasons"] = ai_result["reasons"]

                st.session_state.evaluations.append({
                    "question": str(
                        current_question.get("question", "")
                    ),

                    "final_text": final_answer,

                    "score": round(score, 1),

                    "metrics": metrics,
                })

                st.success(
                    f'Γ£à Answer saved! Transcribed text: "{final_answer}"'
                )

                st.info(
                    f"ML Score: **{score:.1f} / 100** | "
                    f"AI Check: **{ai_result['label']} "
                    f"({ai_result['score']:.0f}%)**"
                )

                st.session_state.current_q_idx += 1

                st.rerun()

            except Exception as exc:

                st.error(
                    f"Answer evaluation failed: {exc}"
                )
