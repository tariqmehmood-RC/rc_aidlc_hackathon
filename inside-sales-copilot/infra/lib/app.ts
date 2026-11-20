import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import { ApiStack } from './api-stack';
import { AuthStack } from './auth-stack';
import { DataStack } from './data-stack';
import { WebStack } from './web-stack';

/** The only region this project uses. It is never read from the shell or from context. */
export const REGION = 'us-east-1';
export const DEFAULT_BACKEND_CODE = path.join(__dirname, '..', '..', 'backend', 'build', 'lambda');

export interface AppOptions {
  /** Folder with the built Lambda bundle. Tests pass a small placeholder folder. */
  backendCodePath?: string;
  context?: Record<string, unknown>;
}

/** Context from cdk.json. The CDK CLI loads it too; reading it here keeps tests and synth the same. */
function fileContext(): Record<string, unknown> {
  const file = path.join(__dirname, '..', 'cdk.json');
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf-8')).context ?? {} : {};
}

export function createApp(options: AppOptions = {}): cdk.App {
  const app = new cdk.App({ context: { ...fileContext(), ...options.context } });
  const env: cdk.Environment = { account: process.env.CDK_DEFAULT_ACCOUNT, region: REGION };
  const ctx = (key: string) => {
    const value = app.node.tryGetContext(key);
    if (value === undefined || value === null || value === '') throw new Error(`cdk.json context "${key}" is missing`);
    return value;
  };

  const backendCodePath = options.backendCodePath ?? DEFAULT_BACKEND_CODE;
  if (!fs.existsSync(path.join(backendCodePath, 'backend', 'src'))) {
    throw new Error(`Lambda bundle not found in ${backendCodePath}. Run scripts/build_backend.sh first.`);
  }
  const tags = { project: 'inside-sales-copilot', team: 'team-5' };

  const auth = new AuthStack(app, 'AuthStack', { env, stackName: 'InsideSalesCopilot-Auth', tags });
  const data = new DataStack(app, 'DataStack', { env, stackName: 'InsideSalesCopilot-Data', tags });
  const api = new ApiStack(app, 'ApiStack', {
    env,
    stackName: 'InsideSalesCopilot-Api',
    tags,
    data,
    userPool: auth.userPool,
    webClient: auth.webClient,
    backendCodePath,
    haikuModelId: ctx('haikuModelId'),
    sonnetModelId: ctx('sonnetModelId'),
    briefModel: ctx('briefModel'),
    researchUserAgent: ctx('researchUserAgent'),
    bedrockRegions: ctx('bedrockRegions'),
  });
  new WebStack(app, 'WebStack', { env, stackName: 'InsideSalesCopilot-Web', tags, api: api.api });
  return app;
}
