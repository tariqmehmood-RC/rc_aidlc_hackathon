import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { createApp } from '../lib/app';

/** A tiny stand-in for the Lambda bundle, so stack tests do not need a real build. */
export function placeholderBundle(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'isc-bundle-'));
  fs.mkdirSync(path.join(dir, 'backend', 'src'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'backend', 'src', '__init__.py'), '');
  return dir;
}

let cached: cdk.App | undefined;
export function testApp(): cdk.App {
  process.env.CDK_DEFAULT_ACCOUNT = '111111111111'; // fake account for synth in tests
  cached = cached ?? createApp({ backendCodePath: placeholderBundle() });
  return cached;
}

export function template(stackId: 'AuthStack' | 'DataStack' | 'ApiStack' | 'WebStack'): Template {
  return Template.fromStack(testApp().node.findChild(stackId) as cdk.Stack);
}

/** All IAM policy statements in a template, flattened. */
export function statements(t: Template): Array<{ Action: string | string[]; Resource: unknown; Effect: string; _policy: string }> {
  const out = [];
  for (const [logicalId, res] of Object.entries(t.findResources('AWS::IAM::Policy'))) {
    for (const s of (res as any).Properties.PolicyDocument.Statement) out.push({ ...s, _policy: logicalId });
  }
  return out;
}

export const asList = (v: string | string[]) => (Array.isArray(v) ? v : [v]);
