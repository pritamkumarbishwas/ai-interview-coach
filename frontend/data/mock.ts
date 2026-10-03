export type InterviewTypeLabel =
  | "Technical"
  | "Behavioral"
  | "HR"
  | "Mixed"
  | "System Design";

export type DifficultyLabel = "Beginner" | "Intermediate" | "Advanced";

export type SessionStatus = "created" | "in_progress" | "completed";

export interface MockInterview {
  id: string;
  role: string;
  type: InterviewTypeLabel;
  difficulty: DifficultyLabel;
  score: number | null;
  date: string;
  status: SessionStatus;
  questions: number;
}

export const MOCK_USER = {
  name: "Jordan Carter",
  email: "jordan.carter@example.com",
  title: "Full Stack Developer",
  memberSince: "September 2026",
};

export const MOCK_STATS = {
  totalInterviews: 12,
  averageScore: 78,
  questionsAnswered: 86,
  practiceTime: "4h 32m",
};

export const MOCK_INTERVIEWS: MockInterview[] = [
  {
    id: "fsd-01",
    role: "Full Stack Developer",
    type: "Technical",
    difficulty: "Intermediate",
    score: null,
    date: "Today",
    status: "in_progress",
    questions: 10,
  },
  {
    id: "fe-02",
    role: "Frontend Developer",
    type: "Technical",
    difficulty: "Intermediate",
    score: 76,
    date: "Yesterday",
    status: "completed",
    questions: 10,
  },
  {
    id: "beh-03",
    role: "Behavioral Interview",
    type: "HR",
    difficulty: "Beginner",
    score: 88,
    date: "Sep 28",
    status: "completed",
    questions: 8,
  },
  {
    id: "sd-04",
    role: "System Design Review",
    type: "System Design",
    difficulty: "Advanced",
    score: 74,
    date: "Sep 26",
    status: "completed",
    questions: 6,
  },
  {
    id: "mix-05",
    role: "Backend Engineer",
    type: "Mixed",
    difficulty: "Advanced",
    score: 80,
    date: "Sep 24",
    status: "completed",
    questions: 12,
  },
  {
    id: "pm-06",
    role: "Product Analyst",
    type: "Behavioral",
    difficulty: "Beginner",
    score: 85,
    date: "Sep 21",
    status: "completed",
    questions: 8,
  },
];

/* ------------------------------------------------------------------ */
/* Active mock session                                                */
/* ------------------------------------------------------------------ */

export interface MockScoreMetric {
  label: string;
  value: number;
}

export interface MockEvaluation {
  overall: number;
  technical: number;
  relevance: number;
  completeness: number;
  clarity: number;
  keyPoints: string[];
  missing: string[];
  suggestion: string;
}

export interface FeedbackItem {
  id: string;
  tone: "good" | "improve";
  title: string;
  detail: string;
}

export interface ChatMessage {
  id: string;
  author: "ai" | "candidate";
  text: string;
  time: string;
}

export const MOCK_SESSION_META = {
  role: "Full Stack Developer",
  type: "Technical Interview",
  questionNumber: 4,
  totalQuestions: 10,
  startElapsedSeconds: 18 * 60 + 42,
};

export const MOCK_SCORES = {
  overall: 82,
  label: "Good",
  metrics: [
    { label: "Technical Accuracy", value: 82 },
    { label: "Relevance", value: 88 },
    { label: "Completeness", value: 76 },
    { label: "Answer Structure", value: 80 },
    { label: "Communication Clarity", value: 78 },
  ] satisfies MockScoreMetric[],
};

export const MOCK_QUESTIONS: string[] = [
  "Explain how you would design a scalable REST API.",
  "How does database indexing improve query performance?",
  "How would you handle authentication and authorization in a web application?",
  "What trade-offs would you consider when choosing between SQL and NoSQL?",
  "How do you ensure a message queue consumer is reliable?",
  "Design a rate limiter for a public API.",
  "How would you implement caching to reduce database load?",
  "How would you debug a service that is returning intermittent 500 errors?",
  "Describe how you would roll out a feature safely to 1% of users.",
  "What makes an API backward compatible?",
];

export const MOCK_CURRENT_QUESTION =
  "Explain how you would design a scalable REST API.";

export const MOCK_CONVERSATION: ChatMessage[] = [
  {
    id: "m1",
    author: "ai",
    text: "Tell me about a challenging project you worked on and how you solved the problem.",
    time: "18:31",
  },
  {
    id: "m2",
    author: "candidate",
    text: "In my last role I led the migration of a monolith to service boundaries. The hardest part was keeping releases stable while we split the billing module — we introduced an anti-corruption layer and dual-wrote data for two weeks before cutting over.",
    time: "18:34",
  },
  {
    id: "m3",
    author: "ai",
    text: "Explain how you would design a scalable REST API.",
    time: "18:39",
  },
  {
    id: "m4",
    author: "candidate",
    text: "I would start by defining the API resources and their relationships, then expose them through consistent endpoints with proper HTTP methods. I would include pagination, versioning, and rate limiting from day one, and keep responses predictable with a uniform error envelope.",
    time: "18:42",
  },
];

export const MOCK_EVALUATION: MockEvaluation = {
  overall: 8.2,
  technical: 8.5,
  relevance: 9.0,
  completeness: 7.5,
  clarity: 8.0,
  keyPoints: [
    "Identified the main problem",
    "Explained implementation",
    "Mentioned scalability",
  ],
  missing: ["Database indexing", "Caching strategy"],
  suggestion:
    "Anchor the answer with one concrete metric — for example: “versioned endpoints let us keep 99.9% uptime during the v1 → v2 migration.” Then close with one sentence on how you would test the design under load.",
};

export const MOCK_FEEDBACK: FeedbackItem[] = [
  {
    id: "f1",
    tone: "good",
    title: "Good structure",
    detail:
      "Your answer followed a clear problem → solution → result structure.",
  },
  {
    id: "f2",
    tone: "good",
    title: "Strong technical explanation",
    detail: "Good explanation of API versioning and pagination choices.",
  },
  {
    id: "f3",
    tone: "improve",
    title: "Consider adding measurable results",
    detail: "Try to explain the impact using specific metrics.",
  },
];

/* Evaluations used when the candidate submits a new answer (mock). */
export const MOCK_FOLLOW_UP_EVALUATIONS: MockEvaluation[] = [
  {
    overall: 8.0,
    technical: 8.5,
    relevance: 8.5,
    completeness: 7.5,
    clarity: 7.5,
    keyPoints: [
      "Answered the core question directly",
      "Used a concrete example",
      "Covered edge cases",
    ],
    missing: ["Monitoring and alerts", "Rollback plan"],
    suggestion:
      "Finish with a short trade-off sentence: name one thing you would deliberately not build yet, and why. It shows senior-level prioritisation.",
  },
  {
    overall: 7.6,
    technical: 8.0,
    relevance: 8.5,
    completeness: 7.0,
    clarity: 7.0,
    keyPoints: [
      "Correct approach",
      "Mentioned relevant tooling",
      "Kept a logical order",
    ],
    missing: ["Performance implications", "Real-world scale numbers"],
    suggestion:
      "Add one quantified detail (traffic, latency, data size) so the interviewer can see the scale you have actually worked with.",
  },
];

export const MOCK_FOLLOW_UP_FEEDBACK: FeedbackItem[][] = [
  [
    {
      id: "n1",
      tone: "good",
      title: "Direct answer",
      detail: "You addressed the question before adding detail.",
    },
    {
      id: "n2",
      tone: "improve",
      title: "Add a concrete metric",
      detail: "Quantify the impact to make the example credible.",
    },
  ],
  [
    {
      id: "n3",
      tone: "good",
      title: "Clear reasoning",
      detail: "The trade-off you described was easy to follow.",
    },
    {
      id: "n4",
      tone: "improve",
      title: "Close with results",
      detail: "End with what changed after your action was applied.",
    },
  ],
];

/* ------------------------------------------------------------------ */
/* Final report                                                       */
/* ------------------------------------------------------------------ */

export const MOCK_REPORT = {
  overall: 82,
  label: "Strong performance",
  role: "Full Stack Developer",
  type: "Technical Interview",
  date: "Today, 18:47",
  duration: "24 min",
  performance: [
    { label: "Technical Accuracy", value: 84 },
    { label: "Communication", value: 78 },
    { label: "Problem Solving", value: 86 },
    { label: "Answer Structure", value: 80 },
  ],
  strongAreas: ["React", "REST APIs", "Problem Solving", "API Versioning"],
  needsImprovement: [
    "System Design",
    "Database Optimization",
    "Behavioral Structure",
  ],
  recommendations: [
    "Practice system design questions",
    "Improve database indexing knowledge",
    "Use measurable results when explaining projects",
  ],
};

export const MOCK_RESULTS: MockInterview[] = MOCK_INTERVIEWS.filter(
  (item) => item.status === "completed",
);

/* ------------------------------------------------------------------ */
/* Resumes & job descriptions (mock)                                   */
/* ------------------------------------------------------------------ */

export interface MockResume {
  id: string;
  fileName: string;
  sizeLabel: string;
  addedAt: string;
}

export interface MockJobDescription {
  id: string;
  title: string;
  company: string;
  snippet: string;
  addedAt: string;
}

export const MOCK_RESUMES: MockResume[] = [
  {
    id: "r1",
    fileName: "jordan-carter-resume.pdf",
    sizeLabel: "412 KB",
    addedAt: "Sep 30, 2026",
  },
  {
    id: "r2",
    fileName: "jordan-carter-resume-ats.docx",
    sizeLabel: "188 KB",
    addedAt: "Sep 18, 2026",
  },
];

export const MOCK_JOB_DESCRIPTIONS: MockJobDescription[] = [
  {
    id: "jd1",
    title: "Senior Full Stack Engineer",
    company: "Northwind Labs",
    snippet:
      "Own features end to end across a React and Node platform serving 2M monthly users. You will design REST services, ship UI with TypeScript, and improve reliability across our payments stack…",
    addedAt: "Today",
  },
  {
    id: "jd2",
    title: "Frontend Developer",
    company: "Brightloop",
    snippet:
      "Build accessible, performant interfaces with React and TypeScript. Partner with design to ship a component library used by five product teams…",
    addedAt: "Sep 27, 2026",
  },
  {
    id: "jd3",
    title: "Backend Engineer",
    company: "Quanta Systems",
    snippet:
      "Design and operate high-throughput services in Node and PostgreSQL. Lead work on caching, queue consumers, and observability…",
    addedAt: "Sep 21, 2026",
  },
];
