import { HttpErrorResponse } from '@angular/common/http';
import { apiErrorMessage } from './api-error';

const httpError = (status: number, error: unknown = null) => new HttpErrorResponse({ status, error });

describe('apiErrorMessage', () => {
  it('uses the fallback for non-HTTP errors', () => {
    expect(apiErrorMessage(new Error('boom'))).toBe('Something went wrong. Please try again.');
    expect(apiErrorMessage('oops', 'Custom fallback')).toBe('Custom fallback');
  });

  it('explains a network failure (status 0)', () => {
    expect(apiErrorMessage(httpError(0))).toBe('Cannot reach the Noesis server. Is the backend running?');
  });

  it('shows a string detail from FastAPI', () => {
    expect(apiErrorMessage(httpError(415, { detail: 'Only PDF files are supported.' }))).toBe(
      'Only PDF files are supported.',
    );
  });

  it('shows the first message of a validation error list', () => {
    const error = { detail: [{ loc: ['body', 'count'], msg: 'Input should be less than 30' }, { msg: 'second' }] };
    expect(apiErrorMessage(httpError(422, error))).toBe('Input should be less than 30');
  });

  it('blames the server for a 5xx without detail', () => {
    expect(apiErrorMessage(httpError(502, '<html>Bad gateway</html>'))).toBe(
      'The Noesis server is not responding or hit an error. Is the backend running?',
    );
  });

  it('prefers the server detail even on a 5xx', () => {
    expect(apiErrorMessage(httpError(503, { detail: 'Groq is unavailable.' }))).toBe('Groq is unavailable.');
  });

  it('uses the fallback for a 4xx without detail', () => {
    expect(apiErrorMessage(httpError(404), 'Not found here.')).toBe('Not found here.');
  });
});
