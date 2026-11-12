import { Routes } from '@angular/router';
import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  // Reserved for authentication: add a LoginPage here and enable AUTH_ENABLED.
  // { path: 'login', loadComponent: () => import('./features/auth/login-page').then((m) => m.LoginPage) },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'library' },
      {
        path: 'library',
        title: 'Library · Noesis',
        loadComponent: () => import('./features/library/library-page').then((m) => m.LibraryPage),
      },
      {
        path: 'study',
        title: 'Study · Noesis',
        loadComponent: () => import('./features/workspace/workspace-page').then((m) => m.WorkspacePage),
      },
      {
        path: 'study/:conversationId',
        title: 'Study · Noesis',
        loadComponent: () => import('./features/workspace/workspace-page').then((m) => m.WorkspacePage),
      },
      {
        path: 'read/:documentId',
        title: 'Reader · Noesis',
        loadComponent: () => import('./features/reader/reader-page').then((m) => m.ReaderPage),
      },
      {
        path: 'quizzes',
        title: 'Quizzes · Noesis',
        loadComponent: () => import('./features/quiz/quiz-list-page').then((m) => m.QuizListPage),
      },
      {
        path: 'quizzes/:quizId',
        title: 'Quiz · Noesis',
        loadComponent: () => import('./features/quiz/quiz-runner-page').then((m) => m.QuizRunnerPage),
      },
      {
        path: 'quizzes/:quizId/attempts/:attemptId',
        title: 'Quiz results · Noesis',
        loadComponent: () => import('./features/quiz/quiz-result-page').then((m) => m.QuizResultPage),
      },
    ],
  },
  { path: '**', redirectTo: 'library' },
];
