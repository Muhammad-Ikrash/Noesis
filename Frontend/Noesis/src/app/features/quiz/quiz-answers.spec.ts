import { AttemptResult, QuizQuestion, QuizQuestionReview } from '../../core/api/models';
import { chosenOptions, correctOptions, isRight, missedQuestions, resultMark } from './quiz-result-page';
import { isAnswered, isPicked, pickOption, validAnswer } from './quiz-runner-page';

function question(kind: QuizQuestion['kind']): QuizQuestion {
  return {
    id: 'q1',
    position: 1,
    kind,
    prompt: '?',
    options: kind === 'true_false' ? ['True', 'False'] : ['A', 'B', 'C', 'D'],
    filename: 'bio.pdf',
    page_number: 1,
  };
}

function review(kind: QuizQuestion['kind'], correct: number[]): QuizQuestionReview {
  return {
    ...question(kind),
    correct_indices: correct,
    correct_index: correct[0],
    explanation: '',
    document_id: 'd1',
    chunk_id: 'c1',
  };
}

describe('quiz runner answers', () => {
  it('treats null and an empty selection as unanswered', () => {
    expect(isAnswered(null)).toBe(false);
    expect(isAnswered([])).toBe(false);
    expect(isAnswered(0)).toBe(true);
    expect(isAnswered([2])).toBe(true);
  });

  it('replaces the answer for single choice and true/false', () => {
    expect(pickOption(question('single'), null, 2)).toBe(2);
    expect(pickOption(question('single'), 2, 1)).toBe(1);
    expect(pickOption(question('true_false'), 0, 1)).toBe(1);
  });

  it('toggles options for multiple choice, kept sorted', () => {
    const q = question('multiple');
    let a = pickOption(q, null, 3);
    a = pickOption(q, a, 0);
    expect(a).toEqual([0, 3]);
    expect(pickOption(q, a, 3)).toEqual([0]);
  });

  it('ignores keys for options the question does not have', () => {
    expect(pickOption(question('true_false'), 0, 3)).toBe(0);
    expect(pickOption(question('single'), null, 4)).toBeNull();
  });

  it('knows which options are picked', () => {
    expect(isPicked(2, 2)).toBe(true);
    expect(isPicked([0, 2], 2)).toBe(true);
    expect(isPicked([0, 2], 1)).toBe(false);
    expect(isPicked(null, 0)).toBe(false);
  });

  it('validates stored draft answers against the question', () => {
    expect(validAnswer(question('single'), null)).toBe(true);
    expect(validAnswer(question('single'), 3)).toBe(true);
    expect(validAnswer(question('single'), [1])).toBe(false);
    expect(validAnswer(question('true_false'), 2)).toBe(false);
    expect(validAnswer(question('multiple'), [0, 3])).toBe(true);
    expect(validAnswer(question('multiple'), 1)).toBe(false);
    expect(validAnswer(question('multiple'), [0, 7])).toBe(false);
  });
});

describe('quiz result grading', () => {
  it('normalises the given answer to a list', () => {
    expect(chosenOptions(null)).toEqual([]);
    expect(chosenOptions(2)).toEqual([2]);
    expect(chosenOptions([1, 3])).toEqual([1, 3]);
  });

  it('falls back to correct_index for older quizzes', () => {
    const old = { ...review('single', [1]), correct_indices: undefined } as unknown as QuizQuestionReview;
    expect(correctOptions(old)).toEqual([1]);
  });

  it('grades single choice and true/false', () => {
    expect(isRight(review('single', [2]), 2)).toBe(true);
    expect(isRight(review('single', [2]), 1)).toBe(false);
    expect(isRight(review('true_false', [1]), 1)).toBe(true);
  });

  it('needs exactly the correct set for multiple choice', () => {
    const q = review('multiple', [0, 2]);
    expect(isRight(q, [2, 0])).toBe(true);
    expect(isRight(q, [0])).toBe(false);
    expect(isRight(q, [0, 1, 2])).toBe(false);
    expect(isRight(q, [])).toBe(false);
  });

  it('labels each result', () => {
    expect(resultMark(review('single', [0]), null)).toBe('Skipped');
    expect(resultMark(review('single', [0]), 0)).toBe('Correct');
    expect(resultMark(review('single', [0]), 1)).toBe('Incorrect');
    expect(resultMark(review('multiple', [0, 2]), [0])).toBe('Incorrect · found 1 of 2');
    expect(resultMark(review('multiple', [0, 2]), [1])).toBe('Incorrect');
  });
});

describe('missedQuestions', () => {
  function attempt(answers: AttemptResult['answers']): AttemptResult {
    const questions = [
      { ...review('single', [0]), id: 'a' },
      { ...review('multiple', [1, 2]), id: 'b' },
      { ...review('true_false', [1]), id: 'c' },
      { ...review('single', [3]), id: 'd' },
    ];
    return { id: 'att', quiz_id: 'q', score: 0, total: 4, answers, created_at: '', questions };
  }

  it('returns wrong and skipped questions in order', () => {
    const missed = missedQuestions(attempt([0, [1], null, 2]));
    expect(missed.map((q) => q.id)).toEqual(['b', 'c', 'd']);
  });

  it('is empty when everything was right', () => {
    expect(missedQuestions(attempt([0, [2, 1], 1, 3]))).toEqual([]);
  });

  it('treats missing answers as skipped', () => {
    expect(missedQuestions(attempt([0, [1, 2]])).map((q) => q.id)).toEqual(['c', 'd']);
  });
});
