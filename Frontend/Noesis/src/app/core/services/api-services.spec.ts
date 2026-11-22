import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DocumentsService } from './documents.service';
import { FlashcardService } from './flashcard.service';
import { QuizService } from './quiz.service';
import { SlidesService } from './slides.service';

/** Each service method must hit the right endpoint with the right verb and body. */
describe('API services', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  function expectCall(method: string, url: string, body?: unknown) {
    const req = backend.expectOne({ method, url });
    if (body !== undefined) expect(req.request.body).toEqual(body);
    req.flush(null);
    return req;
  }

  describe('DocumentsService', () => {
    let svc: DocumentsService;
    beforeEach(() => (svc = TestBed.inject(DocumentsService)));

    it('lists, gets and deletes documents', () => {
      svc.list().subscribe();
      expectCall('GET', '/api/v1/documents');
      svc.get('d1').subscribe();
      expectCall('GET', '/api/v1/documents/d1');
      svc.delete('d1').subscribe();
      expectCall('DELETE', '/api/v1/documents/d1');
    });

    it('uploads the file as multipart form data', () => {
      const file = new File(['%PDF-1.7'], 'notes.pdf', { type: 'application/pdf' });
      svc.upload(file).subscribe();
      const req = backend.expectOne({ method: 'POST', url: '/api/v1/documents' });
      const body = req.request.body as FormData;
      expect(body).toBeInstanceOf(FormData);
      expect((body.get('file') as File).name).toBe('notes.pdf');
      req.flush({});
    });

    it('fetches the PDF bytes as an ArrayBuffer', () => {
      expect(svc.fileUrl('d1')).toBe('/api/v1/documents/d1/file');
      svc.file('d1').subscribe();
      const req = backend.expectOne('/api/v1/documents/d1/file');
      expect(req.request.responseType).toBe('arraybuffer');
      req.flush(new ArrayBuffer(4));
    });
  });

  describe('QuizService', () => {
    let svc: QuizService;
    beforeEach(() => (svc = TestBed.inject(QuizService)));

    it('covers the quiz lifecycle', () => {
      svc.list().subscribe();
      expectCall('GET', '/api/v1/quizzes');
      const create = { document_ids: ['d1'], topic: 'cells', count: 5 };
      svc.create(create as never).subscribe();
      expectCall('POST', '/api/v1/quizzes', create);
      svc.get('q1').subscribe();
      expectCall('GET', '/api/v1/quizzes/q1');
      svc.submit('q1', [0, null, 2]).subscribe();
      expectCall('POST', '/api/v1/quizzes/q1/attempts', { answers: [0, null, 2] });
      svc.attempt('q1', 'a1').subscribe();
      expectCall('GET', '/api/v1/quizzes/q1/attempts/a1');
      svc.retryMissed('q1', 'a1').subscribe();
      expectCall('POST', '/api/v1/quizzes/q1/attempts/a1/retry', {});
      svc.delete('q1').subscribe();
      expectCall('DELETE', '/api/v1/quizzes/q1');
    });
  });

  describe('FlashcardService', () => {
    let svc: FlashcardService;
    beforeEach(() => (svc = TestBed.inject(FlashcardService)));

    it('covers decks, card progress and reset', () => {
      svc.list().subscribe();
      expectCall('GET', '/api/v1/flashcards');
      const create = { document_ids: ['d1'], count: 10 };
      svc.create(create as never).subscribe();
      expectCall('POST', '/api/v1/flashcards', create);
      svc.get('f1').subscribe();
      expectCall('GET', '/api/v1/flashcards/f1');
      svc.mark('f1', 'c1', true).subscribe();
      expectCall('PATCH', '/api/v1/flashcards/f1/cards/c1', { known: true });
      svc.mark('f1', 'c2', false).subscribe();
      expectCall('PATCH', '/api/v1/flashcards/f1/cards/c2', { known: false });
      svc.reset('f1').subscribe();
      expectCall('POST', '/api/v1/flashcards/f1/reset', {});
      svc.delete('f1').subscribe();
      expectCall('DELETE', '/api/v1/flashcards/f1');
    });
  });

  describe('SlidesService', () => {
    let svc: SlidesService;
    beforeEach(() => (svc = TestBed.inject(SlidesService)));

    it('covers create, edit and delete', () => {
      svc.list().subscribe();
      expectCall('GET', '/api/v1/slides');
      const create = { document_ids: ['d1'], count: 8 };
      svc.create(create as never).subscribe();
      expectCall('POST', '/api/v1/slides', create);
      svc.get('s1').subscribe();
      expectCall('GET', '/api/v1/slides/s1');
      svc.update('s1', { title: 'New title' } as never).subscribe();
      expectCall('PATCH', '/api/v1/slides/s1', { title: 'New title' });
      const slides = [{ title: 'One', bullets: ['a'], notes: '' }];
      svc.replaceSlides('s1', slides as never).subscribe();
      expectCall('PUT', '/api/v1/slides/s1/slides', { slides });
      svc.delete('s1').subscribe();
      expectCall('DELETE', '/api/v1/slides/s1');
    });

    it('revises the whole deck or a single slide', () => {
      svc.revise('s1', 'Make it shorter').subscribe();
      expectCall('POST', '/api/v1/slides/s1/revise', { instruction: 'Make it shorter', slide_id: null });
      svc.revise('s1', 'Add an example', 'slide-2').subscribe();
      expectCall('POST', '/api/v1/slides/s1/revise', { instruction: 'Add an example', slide_id: 'slide-2' });
    });

    it('downloads the PowerPoint as an ArrayBuffer', () => {
      svc.pptx('s1').subscribe();
      const req = backend.expectOne('/api/v1/slides/s1/pptx');
      expect(req.request.responseType).toBe('arraybuffer');
      req.flush(new ArrayBuffer(8));
    });
  });
});
