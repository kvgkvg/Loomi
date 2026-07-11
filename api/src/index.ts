import express, { Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import axios from 'axios';
import { z } from 'zod';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;
const CORE_URL = process.env.CORE_URL || 'http://localhost:8000';

app.use(cors());
app.use(express.json());

// Zod schemas for request validation
const RecommendSchema = z.object({
  task_description: z.string().min(1, "Task description cannot be empty"),
  top_k: z.number().int().positive().optional().default(5)
});

const ExplainSchema = z.object({
  asset_id: z.string().uuid("Invalid asset ID format"),
  question: z.string().nullable().optional()
});

const AdoptSchema = z.object({
  asset_id: z.string().uuid("Invalid asset ID format"),
  user_id: z.string().uuid("Invalid user ID format").optional(),
  task_description: z.string().min(1, "Task description cannot be empty")
});

const CaptureSchema = z.object({
  commit_sha: z.string().min(1, "Commit SHA cannot be empty")
});

// Endpoints
app.get('/api/health', async (req: Request, res: Response) => {
  try {
    const coreHealth = await axios.get(`${CORE_URL}/health`, { timeout: 2000 });
    res.json({
      status: 'ok',
      api_gateway: 'ok',
      core_service: coreHealth.data
    });
  } catch (err: any) {
    res.status(503).json({
      status: 'degraded',
      api_gateway: 'ok',
      core_service: {
        status: 'unavailable',
        error: err.message
      }
    });
  }
});

app.get('/api/repo-info', async (req: Request, res: Response) => {
  try {
    const response = await axios.get(`${CORE_URL}/repo-info`, { timeout: 3000 });
    res.json(response.data);
  } catch (err: any) {
    res.status(503).json({ error: err.message });
  }
});

const TrackSchema = z.object({
  repo: z.string().min(1, "Repo cannot be empty")
});

app.post('/api/track', async (req: Request, res: Response) => {
  try {
    const body = TrackSchema.parse(req.body);
    // Cloning a remote repo can take a while; allow a generous timeout.
    const response = await axios.post(`${CORE_URL}/track`, body, { timeout: 120000 });
    res.json(response.data);
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      res.status(400).json({ error: 'Validation failed', details: err.errors });
    } else {
      const status = err.response?.status || 500;
      const message = err.response?.data?.detail || err.message;
      res.status(status).json({ error: message });
    }
  }
});

app.get('/api/asset/:id', async (req: Request, res: Response) => {
  try {
    const response = await axios.get(`${CORE_URL}/asset/${encodeURIComponent(req.params.id)}`, { timeout: 5000 });
    res.json(response.data);
  } catch (err: any) {
    const status = err.response?.status || 500;
    const message = err.response?.data?.detail || err.message;
    res.status(status).json({ error: message });
  }
});

app.post('/api/recommend', async (req: Request, res: Response) => {
  try {
    const body = RecommendSchema.parse(req.body);
    const response = await axios.post(`${CORE_URL}/recommend`, body);
    res.json(response.data);
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      res.status(400).json({ error: 'Validation failed', details: err.errors });
    } else {
      const status = err.response?.status || 500;
      const message = err.response?.data?.detail || err.message;
      res.status(status).json({ error: message });
    }
  }
});

app.post('/api/explain', async (req: Request, res: Response) => {
  try {
    const body = ExplainSchema.parse(req.body);
    const response = await axios.post(`${CORE_URL}/explain`, body);
    res.json(response.data);
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      res.status(400).json({ error: 'Validation failed', details: err.errors });
    } else {
      const status = err.response?.status || 500;
      const message = err.response?.data?.detail || err.message;
      res.status(status).json({ error: message });
    }
  }
});

app.post('/api/adopt', async (req: Request, res: Response) => {
  try {
    const body = AdoptSchema.parse(req.body);
    const response = await axios.post(`${CORE_URL}/adopt`, body);
    res.json(response.data);
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      res.status(400).json({ error: 'Validation failed', details: err.errors });
    } else {
      const status = err.response?.status || 500;
      const message = err.response?.data?.detail || err.message;
      res.status(status).json({ error: message });
    }
  }
});

app.post('/api/capture', async (req: Request, res: Response) => {
  try {
    const body = CaptureSchema.parse(req.body);
    const response = await axios.post(`${CORE_URL}/capture`, body);
    res.json(response.data);
  } catch (err: any) {
    if (err instanceof z.ZodError) {
      res.status(400).json({ error: 'Validation failed', details: err.errors });
    } else {
      const status = err.response?.status || 500;
      const message = err.response?.data?.detail || err.message;
      res.status(status).json({ error: message });
    }
  }
});

// SSE endpoint
app.get('/api/events/stream', async (req: Request, res: Response) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  let coreStream: any = null;

  try {
    const response = await axios({
      method: 'get',
      url: `${CORE_URL}/events`,
      responseType: 'stream',
      timeout: 0 // Disable timeout for SSE
    });

    coreStream = response.data;

    coreStream.on('data', (chunk: Buffer) => {
      res.write(chunk);
    });

    coreStream.on('end', () => {
      res.end();
    });

    coreStream.on('error', (err: any) => {
      console.error('API Gateway: Core stream error:', err.message);
      res.end();
    });

  } catch (err: any) {
    console.error('API Gateway: Failed to connect to core stream:', err.message);
    res.write(`event: error\ndata: ${JSON.stringify({ message: 'Failed to connect to event stream' })}\n\n`);
    res.end();
  }

  req.on('close', () => {
    if (coreStream) {
      coreStream.destroy();
    }
  });
});

if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`API Gateway is running on port ${PORT}`);
  });
}

export default app;
