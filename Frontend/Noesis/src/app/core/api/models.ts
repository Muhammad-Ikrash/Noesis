// Mirrors the backend Pydantic schemas (Backend/src/backend/schemas).

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'missing';
export type LearningMode = 'basic' | 'extensive';
export type RetrievalScope = 'session' | 'library';
export type AnswerStatus = 'answered' | 'insufficient_context' | 'needs_clarification' | 'error';

export interface DocumentOut {
  id: string;
  filename: string;
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  page_count: number | null;
  embedding_model: string | null;
  progress_done: number | null;
  progress_total: number | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  page_number: number;
  char_count: number;
  image_count: number;
  table_count: number;
  needs_ocr: boolean;
}

export interface DocumentDetail extends DocumentOut {
  pages: DocumentPage[];
  ocr_pages: number[];
}

export interface UploadOut {
  document: DocumentOut;
  created: boolean;
}

export interface Source {
  position: number;
  document_id: string | null;
  chunk_id: string | null;
  filename: string;
  page_number: number;
  quote: string | null;
  score: number | null;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  supplementary: string | null;
  mode: LearningMode;
  retrieval_scope: RetrievalScope | null;
  answer_status: AnswerStatus | null;
  needs_clarification: boolean;
  clarification_question: string | null;
  created_at: string;
  sources: Source[];
}

export interface Conversation {
  id: string;
  title: string;
  mode: LearningMode;
  retrieval_scope: RetrievalScope;
  documents: DocumentOut[];
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ConversationCreate {
  title?: string;
  document_ids: string[];
  mode?: LearningMode;
  retrieval_scope?: RetrievalScope;
}

export interface ConversationUpdate {
  title?: string;
  mode?: LearningMode;
  retrieval_scope?: RetrievalScope;
  document_ids?: string[];
}

export interface AskRequest {
  question: string;
  mode: LearningMode;
  retrieval_scope?: RetrievalScope;
}

export interface Retrieved {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number;
  score: number;
}

export interface AskResponse {
  conversation_id: string;
  message_id: string;
  mode: LearningMode;
  retrieval_scope: RetrievalScope;
  answer_status: AnswerStatus;
  answer: string;
  supplementary: string | null;
  needs_clarification: boolean;
  clarification_question: string | null;
  sources: Source[];
  retrieved: Retrieved[];
  searched_document_count: number | null;
  user_message: Message;
}

export interface UserSettings {
  default_retrieval_scope: RetrievalScope;
}

export interface QuizCreate {
  document_ids?: string[];
  conversation_id?: string;
  topic?: string;
  question_count: number;
}

export interface QuizQuestion {
  id: string;
  position: number;
  prompt: string;
  options: string[];
  filename: string;
  page_number: number;
}

export interface QuizQuestionReview extends QuizQuestion {
  correct_index: number;
  explanation: string;
  document_id: string | null;
  chunk_id: string | null;
}

export interface AttemptSummary {
  id: string;
  score: number;
  total: number;
  created_at: string;
}

export interface QuizSummary {
  id: string;
  title: string;
  topic: string | null;
  conversation_id: string | null;
  question_count: number;
  best_score: number | null;
  attempt_count: number;
  created_at: string;
}

export interface Quiz {
  id: string;
  title: string;
  topic: string | null;
  conversation_id: string | null;
  created_at: string;
  questions: QuizQuestion[];
  attempts: AttemptSummary[];
}

export interface AttemptResult {
  id: string;
  quiz_id: string;
  score: number;
  total: number;
  answers: (number | null)[];
  created_at: string;
  questions: QuizQuestionReview[];
}
