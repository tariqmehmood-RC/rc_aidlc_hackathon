import * as fs from 'fs';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import { REGION, createApp } from '../lib/app';

const STACK_NAMES = ['AuthStack', 'DataStack', 'ApiStack', 'WebStack'];

function stacksOf(app: cdk.App): cdk.Stack[] {
  return app.node.children.filter((c): c is cdk.Stack => c instanceof cdk.Stack);
}

describe('app', () => {
  test('has exactly the four stacks', () => {
    expect(stacksOf(createApp()).map((s) => s.node.id).sort()).toEqual([...STACK_NAMES].sort());
  });

  test('every stack is pinned to us-east-1', () => {
    for (const stack of stacksOf(createApp())) {
      expect(stack.region).toBe('us-east-1');
    }
    expect(REGION).toBe('us-east-1');
  });

  test('region is not taken from the shell', () => {
    const saved = { r: process.env.AWS_REGION, d: process.env.AWS_DEFAULT_REGION, c: process.env.CDK_DEFAULT_REGION };
    process.env.AWS_REGION = 'eu-west-1';
    process.env.AWS_DEFAULT_REGION = 'eu-west-1';
    process.env.CDK_DEFAULT_REGION = 'eu-west-1';
    try {
      for (const stack of stacksOf(createApp())) {
        expect(stack.region).toBe('us-east-1');
      }
    } finally {
      for (const [k, v] of [['AWS_REGION', saved.r], ['AWS_DEFAULT_REGION', saved.d], ['CDK_DEFAULT_REGION', saved.c]] as const) {
        if (v === undefined) delete process.env[k]; else process.env[k] = v;
      }
    }
  });
});

describe('cdk.json context', () => {
  const cdkJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'cdk.json'), 'utf-8'));

  test('research user agent default names the project and a contact', () => {
    expect(cdkJson.context.researchUserAgent).toBe(
      'InsideSalesCopilot/0.1 (Royal Cyber AWS AI-DLC hackathon; +https://github.com/tariqmehmood-RC/rc_aidlc_hackathon)',
    );
  });

  test('brief model is haiku or sonnet', () => {
    expect(['haiku', 'sonnet']).toContain(cdkJson.context.briefModel);
  });

  test('model IDs are the tested defaults', () => {
    expect(cdkJson.context.haikuModelId).toBe('us.anthropic.claude-haiku-4-5-20251001-v1:0');
    expect(cdkJson.context.sonnetModelId).toBe('us.anthropic.claude-sonnet-5');
  });
});
