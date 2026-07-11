import request from 'supertest';
import axios from 'axios';
import app from '../src/index';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('Express API Gateway', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/health', () => {
    it('should return ok when core is online', async () => {
      mockedAxios.get.mockResolvedValueOnce({ data: { status: 'ok', database: 'ok', vector_store: 'ok' } });

      const res = await request(app).get('/api/health');

      expect(res.status).toBe(200);
      expect(res.body).toEqual({
        status: 'ok',
        api_gateway: 'ok',
        core_service: { status: 'ok', database: 'ok', vector_store: 'ok' }
      });
      expect(mockedAxios.get).toHaveBeenCalledWith(expect.stringContaining('/health'), expect.any(Object));
    });

    it('should return degraded status when core is offline', async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error('Connection refused'));

      const res = await request(app).get('/api/health');

      expect(res.status).toBe(503);
      expect(res.body.status).toBe('degraded');
      expect(res.body.core_service.status).toBe('unavailable');
    });
  });

  describe('POST /api/recommend', () => {
    it('should proxy recommendation requests and validate payload', async () => {
      const mockResult = [{ asset_id: 'a1', title: 'T1', problem: 'P1', score: 0.8 }];
      mockedAxios.post.mockResolvedValueOnce({ data: mockResult });

      const res = await request(app)
        .post('/api/recommend')
        .send({ task_description: 'I need to classify sales leads', top_k: 3 });

      expect(res.status).toBe(200);
      expect(res.body).toEqual(mockResult);
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/recommend'),
        { task_description: 'I need to classify sales leads', top_k: 3 }
      );
    });

    it('should reject requests with empty description', async () => {
      const res = await request(app)
        .post('/api/recommend')
        .send({ task_description: '', top_k: 3 });

      expect(res.status).toBe(400);
      expect(res.body.error).toBe('Validation failed');
    });
  });

  describe('POST /api/explain', () => {
    const validUuid = '35e6eb7c-acfc-4bfd-a603-e4dd30328cbf';

    it('should proxy explain requests', async () => {
      const mockExplain = { explanation: 'Exp', cited_versions: [1], cited_constraints: [] };
      mockedAxios.post.mockResolvedValueOnce({ data: mockExplain });

      const res = await request(app)
        .post('/api/explain')
        .send({ asset_id: validUuid, question: 'Why?' });

      expect(res.status).toBe(200);
      expect(res.body).toEqual(mockExplain);
    });

    it('should reject invalid UUID format', async () => {
      const res = await request(app)
        .post('/api/explain')
        .send({ asset_id: 'invalid-id' });

      expect(res.status).toBe(400);
      expect(res.body.error).toBe('Validation failed');
    });
  });

  describe('POST /api/adopt', () => {
    const validAssetUuid = '35e6eb7c-acfc-4bfd-a603-e4dd30328cbf';
    const validUserUuid = 'e8b7c4a1-dbca-49f3-8ad4-1dfd22384a51';

    it('should proxy adopt requests', async () => {
      mockedAxios.post.mockResolvedValueOnce({ data: { status: 'success', usage_id: 'u1' } });

      const res = await request(app)
        .post('/api/adopt')
        .send({
          asset_id: validAssetUuid,
          user_id: validUserUuid,
          task_description: 'Adopting lead classifier'
        });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
    });

    it('should reject invalid asset ID or empty task description', async () => {
      const res = await request(app)
        .post('/api/adopt')
        .send({
          asset_id: 'invalid-uuid',
          task_description: ''
        });

      expect(res.status).toBe(400);
    });
  });

  describe('POST /api/intent-review', () => {
    it('should forward prompt review payload with chat history', async () => {
      const mockReview = { id: 'r1', status: 'pending', checks: [], intent: 'Do task' };
      mockedAxios.post.mockResolvedValueOnce({ data: mockReview });

      const res = await request(app)
        .post('/api/intent-review')
        .send({
          prompt: 'Refactor onboarding flow',
          source_env: 'codex',
          chat_history: ['first message', 'second message']
        });

      expect(res.status).toBe(200);
      expect(res.body).toEqual(mockReview);
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/intent-review'),
        {
          prompt: 'Refactor onboarding flow',
          source_env: 'codex',
          chat_history: ['first message', 'second message']
        },
        { timeout: 120000 }
      );
    });
  });

  describe('POST /api/rationale-review/version/:id/approve', () => {
    it('should forward rationale approve requests', async () => {
      mockedAxios.post.mockResolvedValueOnce({
        data: { status: 'approved', version_id: 'v1', reviewed: 2 }
      });

      const res = await request(app)
        .post('/api/rationale-review/version/v1/approve')
        .send({ reviewer: 'Reviewer' });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('approved');
      expect(mockedAxios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rationale-review/version/v1/approve'),
        { reviewer: 'Reviewer' },
        { timeout: 120000 }
      );
    });
  });
});
