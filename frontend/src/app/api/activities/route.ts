export async function GET() {
  // Atualiza o access token
  const tokenResponse = await fetch("https://www.strava.com/oauth/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      client_id: "262271",
      client_secret: "d5c36f980ba41ff448f5f27deb700dda19170251",
      refresh_token:
        "dac23906235bbacb863b8420d1db34f63836b239",
      grant_type: "refresh_token",
    }),
  });

  const tokenData = await tokenResponse.json();

  const activities = await fetch(
    "https://www.strava.com/api/v3/athlete/activities?per_page=1",
    {
      headers: {
        Authorization: `Bearer ${tokenData.access_token}`,
      },
    }
  );

  const data = await activities.json();

  return Response.json(data);
}